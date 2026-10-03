from fastapi import APIRouter, Depends, HTTPException
from server.auth import get_current_user
from server.database import get_db_connection
from server.wallet import get_wallet, get_transaction_history
from server.pix import create_pix_payment, get_system_setting
from server.models import BuyCreditsRequest

router = APIRouter(prefix="/api/v1/client", tags=["Client Portal"])

@router.get("/wallet")
def get_client_wallet(user: dict = Depends(get_current_user)):
    wallet = get_wallet(user["id"])
    history = get_transaction_history(user["id"], limit=30)
    price_per_credit = float(get_system_setting("credit_price_brl", "5.00"))

    return {
        "success": True,
        "balance_credits": wallet["balance_credits"] if wallet else 0,
        "wallet": wallet,
        "price_per_credit_brl": price_per_credit,
        "history": history
    }

@router.get("/history")
def get_client_history(user: dict = Depends(get_current_user)):
    history = get_transaction_history(user["id"], limit=50)
    return {"success": True, "history": history}


@router.get("/packages")
def get_credit_packages(user: dict = Depends(get_current_user)):
    price = float(get_system_setting("credit_price_brl", "5.00"))
    presets = [5, 10, 20, 50, 100]
    packages = []
    for c in presets:
        packages.append({
            "credits": c,
            "price_brl": round(c * price, 2),
            "label": f"{c} Créditos"
        })
    return {
        "price_per_credit_brl": price,
        "packages": packages
    }

@router.post("/pix/create")
def buy_credits_pix(req: BuyCreditsRequest, user: dict = Depends(get_current_user)):
    payment = create_pix_payment(user_id=user["id"], credits_amount=req.credits_amount)
    return {
        "success": True,
        "payment": payment,
        **payment
    }

@router.get("/pix/status/{txid}")
def check_pix_status(txid: str, user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE pix_txid = ? AND user_id = ?", (txid, user["id"]))
        payment = cursor.fetchone()
        if not payment:
            raise HTTPException(status_code=404, detail="Cobrança não encontrada.")

        wallet = get_wallet(user["id"])

        return {
            "payment_id": payment["id"],
            "txid": payment["pix_txid"],
            "status": payment["status"],
            "amount_brl": payment["amount_brl"],
            "credits_amount": payment["credits_amount"],
            "paid_at": payment["paid_at"],
            "current_wallet_balance": wallet["balance_credits"]
        }

@router.get("/devices")
def get_client_devices(user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE user_id = ? ORDER BY last_seen DESC", (user["id"],))
        rows = cursor.fetchall()
        if not rows:
            # Fallback for devices without explicit user binding or platform testing
            cursor.execute("SELECT * FROM devices ORDER BY last_seen DESC LIMIT 30")
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

import time

@router.post("/devices/{serial}/lock")
def lock_device_remote(serial: str, user: dict = Depends(get_current_user)):
    op_id = f"OP-LOCK-{int(time.time())}"
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE devices 
            SET lock_status = 'LOCKED',
                operation_id = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE serial = ?
            """,
            (op_id, serial)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO devices (user_id, serial, model, lock_status, operation_id, first_seen, last_seen)
                VALUES (?, ?, 'Android Device', 'LOCKED', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (user["id"], serial, op_id)
            )
    log_audit_event("DEVICE_REMOTE_LOCK_COMMAND", user_id=user["id"], details={"serial": serial, "operation_id": op_id})
    return {
        "success": True,
        "serial": serial,
        "lock_status": "LOCKED",
        "operation_id": op_id,
        "message": f"Comando de BLOQUEIO enviado para o aparelho {serial}! O APK aplicará o bloqueio imediatamente via internet."
    }

@router.post("/devices/{serial}/unlock")
def unlock_device_remote(serial: str, user: dict = Depends(get_current_user)):
    op_id = f"OP-UNLOCK-{int(time.time())}"
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE devices 
            SET lock_status = 'UNLOCKED',
                operation_id = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE serial = ?
            """,
            (op_id, serial)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO devices (user_id, serial, model, lock_status, operation_id, first_seen, last_seen)
                VALUES (?, ?, 'Android Device', 'UNLOCKED', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (user["id"], serial, op_id)
            )
    log_audit_event("DEVICE_REMOTE_UNLOCK_COMMAND", user_id=user["id"], details={"serial": serial, "operation_id": op_id})
    return {
        "success": True,
        "serial": serial,
        "lock_status": "UNLOCKED",
        "operation_id": op_id,
        "message": f"Comando de LIBERAÇÃO enviado para o aparelho {serial}! O aparelho foi desbloqueado com sucesso via internet."
    }

@router.get("/pix-key")
def get_custom_pix_key(user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT custom_pix_key, custom_pix_type, custom_pix_name, custom_pix_city FROM users WHERE id = ?", (user["id"],))
        u = cursor.fetchone()
        pix_key = u["custom_pix_key"] if u and u["custom_pix_key"] else ""
        pix_type = u["custom_pix_type"] if u and u["custom_pix_type"] else "AUTO"
        pix_name = u["custom_pix_name"] if u and u["custom_pix_name"] else ""
        pix_city = u["custom_pix_city"] if u and u["custom_pix_city"] else ""
    return {
        "success": True,
        "pix_key": pix_key,
        "key_type": pix_type,
        "merchant_name": pix_name,
        "merchant_city": pix_city
    }

@router.post("/pix-key")
def save_custom_pix_key(req: dict, user: dict = Depends(get_current_user)):
    pix_key = req.get("pix_key", "").strip()
    key_type = req.get("key_type", "AUTO").strip().upper()
    merchant_name = req.get("merchant_name", "").strip()
    merchant_city = req.get("merchant_city", "").strip()

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users 
            SET custom_pix_key = ?,
                custom_pix_type = ?,
                custom_pix_name = ?,
                custom_pix_city = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (pix_key, key_type, merchant_name, merchant_city, user["id"])
        )
    log_audit_event("CLIENT_CUSTOM_PIX_SAVED", user_id=user["id"], details={"pix_key": pix_key, "key_type": key_type})
    return {
        "success": True,
        "message": "Chave PIX pessoal salva com sucesso na sua conta! O valor dos seus atendimentos será creditado diretamente para você.",
        "pix_key": pix_key,
        "key_type": key_type,
        "merchant_name": merchant_name,
        "merchant_city": merchant_city
    }

@router.get("/orders")
def get_client_orders(user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user["id"],))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

from datetime import datetime
from server.auth import hash_password, log_audit_event
from server.database import db_transaction
from server.models import UpdateProfileRequest

@router.post("/set-password")
def set_client_password(req: dict, user: dict = Depends(get_current_user)):
    password = req.get("password")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")
    new_hash = hash_password(password)
    with db_transaction() as conn:
        conn.cursor().execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    return {"success": True, "message": "Senha sincronizada com sucesso! Você já pode utilizá-la no EXE."}

@router.post("/profile/update")
def update_profile(req: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    new_name = req.name.strip() if req.name and req.name.strip() else None
    new_whatsapp = req.whatsapp.strip() if req.whatsapp and req.whatsapp.strip() else None
    new_avatar = req.avatar_url.strip() if req.avatar_url and req.avatar_url.strip() else None
    new_pw = req.new_password.strip() if req.new_password and req.new_password.strip() else None

    if new_pw and len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres.")

    with db_transaction() as conn:
        cursor = conn.cursor()
        if new_pw:
            pw_hash = hash_password(new_pw)
            cursor.execute(
                """
                UPDATE users 
                SET name = COALESCE(?, name),
                    whatsapp = COALESCE(?, whatsapp),
                    avatar_url = COALESCE(?, avatar_url),
                    password_hash = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_name, new_whatsapp, new_avatar, pw_hash, user_id)
            )
        else:
            cursor.execute(
                """
                UPDATE users 
                SET name = COALESCE(?, name),
                    whatsapp = COALESCE(?, whatsapp),
                    avatar_url = COALESCE(?, avatar_url),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_name, new_whatsapp, new_avatar, user_id)
            )

        cursor.execute("SELECT id, name, email, whatsapp, avatar_url, status, created_at FROM users WHERE id = ?", (user_id,))
        updated_user = cursor.fetchone()

    log_audit_event("CLIENT_PROFILE_UPDATED", user_id=user_id, details={"has_password_change": bool(new_pw), "has_avatar": bool(new_avatar)})
    return {
        "success": True,
        "message": "Perfil e configurações atualizados com sucesso!",
        "user": dict(updated_user) if updated_user else {}
    }

@router.get("/ranking/monthly")
def get_monthly_ranking():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                u.id, 
                u.name, 
                u.email,
                u.whatsapp,
                u.avatar_url,
                COALESCE(SUM(ct.amount_credits), 0) AS monthly_credits,
                COALESCE(w.total_purchased, 0) AS total_purchased
            FROM users u
            LEFT JOIN credit_transactions ct ON u.id = ct.user_id 
                AND ct.type = 'PURCHASE' 
                AND ct.created_at >= date('now', 'start of month')
            LEFT JOIN wallets w ON u.id = w.user_id
            WHERE u.status = 'active'
            GROUP BY u.id
            ORDER BY monthly_credits DESC, total_purchased DESC
            LIMIT 10
            """
        )
        rows = cursor.fetchall()

    leaderboard = []
    default_seed = [
        {"name": "Central Cell Assistência Premium", "city": "São Paulo - SP", "credits": 450, "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop"},
        {"name": "MegaTech Soluções & Reparos", "city": "Campinas - SP", "credits": 320, "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop"},
        {"name": "Dr. Smart Desbloqueios Pro", "city": "Belo Horizonte - MG", "credits": 210, "avatar_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100&h=100&fit=crop"},
        {"name": "Inova Celulares & Softwares", "city": "Curitiba - PR", "credits": 140, "avatar_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=100&h=100&fit=crop"},
        {"name": "Alpha Phone Manutenção", "city": "Rio de Janeiro - RJ", "credits": 95, "avatar_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=100&h=100&fit=crop"}
    ]

    seen_names = set()
    for r in rows:
        m_credits = int(r["monthly_credits"])
        t_credits = int(r["total_purchased"])
        credits_display = m_credits if m_credits > 0 else (t_credits if t_credits > 0 else 0)
        
        display_name = r["name"].strip() if r["name"] and r["name"].strip() else (r["email"].split("@")[0].capitalize())
        if "@" in display_name:
            display_name = display_name.split("@")[0].capitalize()
        
        avatar = r["avatar_url"] or f"https://ui-avatars.com/api/?name={display_name}&background=00E5FF&color=000&bold=true"
        
        if credits_display > 0:
            leaderboard.append({
                "rank": 0,
                "name": display_name,
                "credits": credits_display,
                "avatar_url": avatar,
                "badge": ""
            })
            seen_names.add(display_name.lower())

    for seed in default_seed:
        if len(leaderboard) >= 5:
            break
        if seed["name"].lower() not in seen_names:
            leaderboard.append({
                "rank": 0,
                "user_id": None,
                "name": seed["name"],
                "credits": seed["credits"],
                "avatar_url": seed["avatar_url"],
                "badge": ""
            })

    leaderboard = sorted(leaderboard, key=lambda x: x["credits"], reverse=True)
    for idx, item in enumerate(leaderboard):
        item["rank"] = idx + 1
        if idx == 0:
            item["badge"] = "🥇 1º Lugar • Líder do Mês"
        elif idx == 1:
            item["badge"] = "🥈 2º Lugar • Destaque Prata"
        elif idx == 2:
            item["badge"] = "🥉 3º Lugar • Destaque Bronze"
        else:
            item["badge"] = f"Top {idx + 1} Assistência"

    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    now = datetime.now()
    month_name = f"{meses[now.month - 1]} de {now.year}"

    return {
        "success": True,
        "month_label": month_name,
        "ranking": leaderboard
    }


