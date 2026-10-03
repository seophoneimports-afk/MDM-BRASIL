import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from server.auth import verify_password, create_access_token, get_current_user, log_audit_event
from server.database import get_db_connection, db_transaction
from server.wallet import consume_credits, get_wallet, InsufficientCreditsError
from server.models import ExeLoginRequest, ExeConsumeRequest

router = APIRouter(prefix="/api/v1/exe", tags=["Windows EXE Integration"])

@router.post("/auth/login")
def exe_login(req: ExeLoginRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()

        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

        if user["status"] == "suspended":
            raise HTTPException(status_code=403, detail="Esta conta está suspensa. Entre em contato com o suporte.")

        user_id = user["id"]
        cursor.execute("SELECT balance_credits FROM wallets WHERE user_id = ?", (user_id,))
        w = cursor.fetchone()
        balance = w["balance_credits"] if w else 0

    log_audit_event("EXE_CLIENT_LOGIN", user_id=user_id, details={"email": email_clean}, ip_address=client_ip)

    token = create_access_token({"user_id": user_id, "role": "client", "email": email_clean})
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "name": user["name"],
            "email": user["email"],
            "whatsapp": user["whatsapp"],
            "balance_credits": balance
        }
    }

@router.get("/wallet/balance")
def exe_get_balance(user: dict = Depends(get_current_user)):
    wallet = get_wallet(user["id"])
    return {
        "success": True,
        "user_id": user["id"],
        "name": user["name"],
        "balance_credits": wallet["balance_credits"],
        "total_used": wallet["total_used"]
    }

@router.post("/services/consume")
def exe_consume_service(req: ExeConsumeRequest, request: Request, user: dict = Depends(get_current_user)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_id = user["id"]
    required_credits = req.credits_to_consume
    op_id = f"OP-{int(time.time())}-{uuid.uuid4().hex[:4]}".upper()

    try:
        desc = f"Serviço {req.service_name} ({req.device_model} / Serial: {req.device_serial})"
        tx = consume_credits(
            user_id=user_id,
            amount=required_credits,
            description=desc,
            reference_id=op_id
        )
    except InsufficientCreditsError as e:
        wallet = get_wallet(user_id)
        return {
            "authorized": False,
            "error": "INSUFFICIENT_CREDITS",
            "message": str(e),
            "current_balance": wallet["balance_credits"],
            "required_credits": required_credits
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Erro ao processar consumo de créditos: {str(ex)}")

    # Record order and upsert device in database
    with db_transaction() as conn:
        cursor = conn.cursor()

        # Upsert device
        cursor.execute(
            """
            INSERT INTO devices (user_id, serial, model, manufacturer, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, serial) DO UPDATE SET
                model = excluded.model,
                last_seen = CURRENT_TIMESTAMP
            """,
            (user_id, req.device_serial, req.device_model, req.device_model.split()[0] if req.device_model else "Android")
        )

        # Insert service order
        cursor.execute(
            """
            INSERT INTO orders (
                user_id, device_serial, device_model, service_code, service_name,
                credit_cost, operation_id, status, client_name, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?)
            """,
            (
                user_id, req.device_serial, req.device_model, req.service_code,
                req.service_name, required_credits, op_id, req.client_name,
                f"Consumo de {required_credits} crédito(s) via EXE"
            )
        )

    log_audit_event(
        "EXE_SERVICE_AUTHORIZED",
        user_id=user_id,
        details={
            "device_serial": req.device_serial,
            "device_model": req.device_model,
            "operation_id": op_id,
            "credits_consumed": required_credits,
            "new_balance": tx["new_balance"]
        },
        ip_address=client_ip
    )

    return {
        "authorized": True,
        "operation_id": op_id,
        "service_code": req.service_code,
        "credits_consumed": required_credits,
        "previous_balance": tx["previous_balance"],
        "new_balance": tx["new_balance"],
        "transaction_id": tx["transaction_id"],
        "message": f"Serviço autorizado com sucesso! 1 crédito consumido. Saldo restante: {tx['new_balance']} créditos."
    }

@router.get("/pix/config")
def exe_get_pix_config(user: dict = Depends(get_current_user)):
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'pix_key'")
        r_sys = cursor.fetchone()
        sys_key = r_sys["value"] if r_sys and r_sys["value"] else "19994783127"

        cursor.execute("SELECT config_value FROM platform_configs WHERE config_key = 'pix_settings'")
        row = cursor.fetchone()
        if row and row["config_value"]:
            try:
                pix_cfg = json.loads(row["config_value"])
            except Exception:
                pix_cfg = {"key": sys_key, "key_type": "TELEFONE", "merchant_name": "MDM FRP BRASIL", "merchant_city": "AMERICANA"}
        else:
            pix_cfg = {
                "key": sys_key,
                "key_type": "TELEFONE",
                "merchant_name": "MDM FRP BRASIL",
                "merchant_city": "AMERICANA"
            }
    return {
        "success": True,
        "pix_key": pix_cfg.get("key"),
        "key_type": pix_cfg.get("key_type", "TELEFONE"),
        "merchant_name": pix_cfg.get("merchant_name", "MDM FRP BRASIL"),
        "merchant_city": pix_cfg.get("merchant_city", "AMERICANA")
    }
