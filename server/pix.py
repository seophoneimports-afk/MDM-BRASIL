import io
import time
import uuid
import base64
import qrcode
from datetime import datetime, timedelta
from fastapi import HTTPException
from server.database import get_db_connection, db_transaction
from server.wallet import add_credits

def calc_crc16(payload: str) -> str:
    """Calcula o CRC16-CCITT (0xFFFF) no padrão do Banco Central do Brasil."""
    crc = 0xFFFF
    for char in payload.encode('utf-8'):
        crc ^= (char << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

import re
import unicodedata

def sanitize_ascii(text: str, max_len: int) -> str:
    """Remove acentos e caracteres especiais para total conformidade EMV / BACEN."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', ascii_text).strip().upper()
    return clean[:max_len]

def format_pix_key(key: str, key_type: str = "AUTO") -> str:
    """Formata qualquer chave PIX no padrão do Banco Central (BACEN)."""
    if not key:
        return ""
    raw = key.strip()
    digits = re.sub(r'\D', '', raw)

    kt = (key_type or "AUTO").upper()

    if kt == "TELEFONE":
        if digits.startswith("55") and len(digits) in (12, 13):
            return f"+{digits}"
        elif len(digits) in (10, 11):
            return f"+55{digits}"
        elif raw.startswith("+"):
            return raw
        return f"+55{digits}" if digits else raw
    elif kt == "CPF":
        return digits[:11]
    elif kt == "CNPJ":
        return digits[:14]
    elif kt == "EMAIL":
        return raw.lower()
    elif kt == "ALEATORIA":
        return raw.lower()
    else:  # AUTO
        if "@" in raw:
            return raw.lower()
        if len(digits) == 14:
            return digits  # CNPJ
        if raw.startswith("+") or raw.startswith("(") or (digits.startswith("55") and len(digits) in (12, 13)):
            return f"+{digits}" if not raw.startswith("+") else raw
        if len(digits) in (10, 11) and (raw.startswith("1") or raw.startswith("2") or raw.startswith("3") or raw.startswith("4") or raw.startswith("5") or raw.startswith("6") or raw.startswith("7") or raw.startswith("8") or raw.startswith("9")):
            # Se tiver 11 dígitos e começar com DDD válido (ex: 11..99) e conter formatação de celular ou 9 dígitos
            if len(digits) == 11 and digits[2] == '9':
                return f"+55{digits}"
            return digits  # CPF
        if "-" in raw and len(raw) >= 32:
            return raw.lower()  # Chave Aleatória / EVP
        return raw

def generate_pix_copia_e_cola(pix_key: str, amount: float, txid: str, merchant_name: str = "MDM FRP BRASIL", merchant_city: str = "AMERICANA") -> str:
    def emv(tag: str, val: str) -> str:
        return f"{tag}{len(val):02d}{val}"

    # Tag 26: Merchant Account Information - Pix
    gui = emv("00", "br.gov.bcb.pix")
    key = emv("01", pix_key)
    tag26 = emv("26", gui + key)

    safe_name = sanitize_ascii(merchant_name, 25) or "MDM FRP BRASIL"
    safe_city = sanitize_ascii(merchant_city, 15) or "AMERICANA"
    safe_txid = re.sub(r'[^a-zA-Z0-9]', '', txid)[:25] or "***"

    payload = (
        emv("00", "01") +                # Payload Format Indicator
        emv("01", "11") +                # Point of Initiation: 11 = Estático com valor (compatível 100% dos apps bancários)
        tag26 +
        emv("52", "0000") +              # Merchant Category Code
        emv("53", "986") +               # Transaction Currency (986 = BRL)
        emv("54", f"{amount:.2f}") +     # Transaction Amount
        emv("58", "BR") +                # Country Code
        emv("59", safe_name) +           # Merchant Name
        emv("60", safe_city) +           # Merchant City
        emv("62", emv("05", safe_txid))  # Additional Data Field Template (txid)
    )

    payload_with_crc_tag = payload + "6304"
    crc = calc_crc16(payload_with_crc_tag)
    return payload_with_crc_tag + crc

def generate_qr_base64(payload: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def get_system_setting(key: str, default: str = "") -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def create_pix_payment(user_id: int, credits_amount: int) -> dict:
    if credits_amount <= 0:
        raise HTTPException(status_code=400, detail="Quantidade de créditos inválida.")

    price_per_credit = float(get_system_setting("credit_price_brl", "5.00"))
    amount_brl = round(credits_amount * price_per_credit, 2)
    raw_pix_key = get_system_setting("pix_key", "19994783127")
    key_type = get_system_setting("pix_key_type", "AUTO")
    pix_key = format_pix_key(raw_pix_key, key_type)

    merchant_name = get_system_setting("pix_merchant_name", "MDM FRP BRASIL")
    merchant_city = get_system_setting("pix_merchant_city", "AMERICANA")

    txid = f"MDM{int(time.time())}{uuid.uuid4().hex[:6]}".upper()
    copia_e_cola = generate_pix_copia_e_cola(pix_key, amount_brl, txid, merchant_name, merchant_city)
    qr_base64 = generate_qr_base64(copia_e_cola)

    expires_at = datetime.utcnow() + timedelta(minutes=30)

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO payments (
                user_id, amount_brl, credits_amount, pix_key, pix_txid,
                pix_copia_e_cola, qr_code_base64, status, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (user_id, amount_brl, credits_amount, pix_key, txid, copia_e_cola, qr_base64, expires_at)
        )
        payment_id = cursor.lastrowid

    bonus_credits = int(credits_amount) // 5
    return {
        "payment_id": payment_id,
        "txid": txid,
        "amount_brl": amount_brl,
        "credits_amount": credits_amount,
        "bonus_credits": bonus_credits,
        "total_credits": credits_amount + bonus_credits,
        "pix_copia_e_cola": copia_e_cola,
        "qr_code_base64": qr_base64,
        "expires_at": expires_at.isoformat(),
        "status": "PENDING"
    }

def process_pix_webhook(txid: str, idempotency_key: str, raw_payload: str, event_status: str = "PAID") -> dict:
    """
    Idempotent processing of PIX webhook notification.
    Ensures credits are awarded strictly once.
    """
    with db_transaction() as conn:
        cursor = conn.cursor()

        # 1. Check if idempotency key already processed
        cursor.execute("SELECT * FROM payment_webhooks WHERE idempotency_key = ?", (idempotency_key,))
        existing_wh = cursor.fetchone()
        if existing_wh:
            return {
                "success": True,
                "message": "Notificação já processada anteriormente (idempotente).",
                "status": existing_wh["status"]
            }

        # 2. Find payment by txid
        cursor.execute("SELECT * FROM payments WHERE pix_txid = ?", (txid,))
        payment = cursor.fetchone()
        if not payment:
            # Register unknown webhook
            cursor.execute(
                "INSERT INTO payment_webhooks (payment_id, idempotency_key, raw_payload, status) VALUES (NULL, ?, ?, 'NOT_FOUND')",
                (idempotency_key, raw_payload)
            )
            raise HTTPException(status_code=404, detail="Cobrança PIX não encontrada para este txid.")

        payment_id = payment["id"]
        current_status = payment["status"]
        user_id = payment["user_id"]
        credits_to_add = payment["credits_amount"]

        if current_status == "PAID":
            # Already paid, log webhook and return success
            cursor.execute(
                "INSERT INTO payment_webhooks (payment_id, idempotency_key, raw_payload, status) VALUES (?, ?, ?, 'ALREADY_PAID')",
                (payment_id, idempotency_key, raw_payload)
            )
            return {
                "success": True,
                "message": "Pagamento já estava aprovado e créditos creditados.",
                "status": "PAID"
            }

        if event_status == "PAID":
            # Update payment record
            cursor.execute(
                "UPDATE payments SET status = 'PAID', paid_at = CURRENT_TIMESTAMP WHERE id = ?",
                (payment_id,)
            )

            # Record webhook
            cursor.execute(
                "INSERT INTO payment_webhooks (payment_id, idempotency_key, raw_payload, status) VALUES (?, ?, ?, 'PROCESSED')",
                (payment_id, idempotency_key, raw_payload)
            )

    # 3. Add credits outside the lock or in clean transaction:
    # REGRA INVIOLÁVEL: A cada 5 créditos adquiridos, +1 bônus grátis automático (+2 para 10, +3 para 15, +4 para 20, etc.)
    bonus_credits = int(credits_to_add) // 5

    desc = f"Recarga PIX ({credits_to_add} créditos) - TXID: {txid}"
    tx_rec = add_credits(user_id, credits_to_add, "PURCHASE", desc, reference_id=txid)

    if bonus_credits > 0:
        bonus_desc = f"🎁 Bônus Fidelidade Automático (+{bonus_credits} Grátis a cada 5) - TXID: {txid}"
        tx_bonus = add_credits(user_id, bonus_credits, "BONUS", bonus_desc, reference_id=f"BONUS_{txid}")
        final_balance = tx_bonus["new_balance"]
    else:
        final_balance = tx_rec["new_balance"]

    return {
        "success": True,
        "message": f"Pagamento confirmado com sucesso! {credits_to_add} créditos (+{bonus_credits} bônus grátis) adicionados à carteira.",
        "status": "PAID",
        "credits_added": credits_to_add,
        "bonus_credits": bonus_credits,
        "total_credits_added": credits_to_add + bonus_credits,
        "new_balance": final_balance
    }
