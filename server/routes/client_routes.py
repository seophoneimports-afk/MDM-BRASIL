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
        return [dict(r) for r in rows]

@router.get("/orders")
def get_client_orders(user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user["id"],))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

@router.post("/set-password")
def set_client_password(req: dict, user: dict = Depends(get_current_user)):
    from server.auth import hash_password
    from server.database import db_transaction
    password = req.get("password")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")
    new_hash = hash_password(password)
    with db_transaction() as conn:
        conn.cursor().execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    return {"success": True, "message": "Senha sincronizada com sucesso! Você já pode utilizá-la no EXE."}

