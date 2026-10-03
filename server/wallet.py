from datetime import datetime
from fastapi import HTTPException
from server.database import db_transaction, get_db_connection

class InsufficientCreditsError(Exception):
    def __init__(self, message="Saldo insuficiente de créditos para esta operação."):
        super().__init__(message)

def get_wallet(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,))
        wallet = cursor.fetchone()
        if not wallet:
            # Create wallet if missing
            with db_transaction() as t_conn:
                t_conn.cursor().execute(
                    "INSERT OR IGNORE INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, 0, 0, 0, 0)",
                    (user_id,)
                )
            cursor.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,))
            wallet = cursor.fetchone()
        return dict(wallet)

def add_credits(user_id: int, amount: int, tx_type: str, description: str, reference_id: str = None) -> dict:
    """
    Atomically adds credits to the user's wallet and records transaction.
    tx_type: 'PURCHASE', 'BONUS', 'ADJUSTMENT', 'REFUND'
    """
    if amount <= 0:
        raise ValueError("Quantidade de créditos deve ser maior que zero.")

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, 0, 0, 0, 0)",
                (user_id,)
            )
            prev_balance = 0
            prev_purchased = 0
            wallet_id = cursor.lastrowid
        else:
            wallet_id = row["id"]
            prev_balance = row["balance_credits"]
            prev_purchased = row["total_purchased"]

        new_balance = prev_balance + amount
        new_purchased = prev_purchased + amount if tx_type == "PURCHASE" else prev_purchased

        cursor.execute(
            """
            UPDATE wallets
            SET balance_credits = ?, total_purchased = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_balance, new_purchased, wallet_id)
        )

        cursor.execute(
            """
            INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (wallet_id, user_id, tx_type, amount, prev_balance, new_balance, description, reference_id)
        )
        tx_id = cursor.lastrowid

        return {
            "transaction_id": tx_id,
            "user_id": user_id,
            "type": tx_type,
            "amount_credits": amount,
            "previous_balance": prev_balance,
            "new_balance": new_balance,
            "description": description,
            "reference_id": reference_id
        }

def consume_credits(user_id: int, amount: int = 1, description: str = "Serviço MDM/FRP", reference_id: str = None) -> dict:
    """
    Atomically checks balance and consumes credits.
    Prevents negative balance.
    """
    if amount <= 0:
        raise ValueError("Quantidade a debitar deve ser maior que zero.")

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise InsufficientCreditsError("Carteira não encontrada. Saldo 0.")

        wallet_id = row["id"]
        prev_balance = row["balance_credits"]
        prev_used = row["total_used"]

        if prev_balance < amount:
            raise InsufficientCreditsError(f"Saldo insuficiente. Disponível: {prev_balance} créditos. Necessário: {amount} créditos.")

        new_balance = prev_balance - amount
        new_used = prev_used + amount

        cursor.execute(
            """
            UPDATE wallets
            SET balance_credits = ?, total_used = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_balance, new_used, wallet_id)
        )

        cursor.execute(
            """
            INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
            VALUES (?, ?, 'CONSUMPTION', ?, ?, ?, ?, ?)
            """,
            (wallet_id, user_id, amount, prev_balance, new_balance, description, reference_id)
        )
        tx_id = cursor.lastrowid

        return {
            "transaction_id": tx_id,
            "user_id": user_id,
            "amount_debited": amount,
            "previous_balance": prev_balance,
            "new_balance": new_balance,
            "reference_id": reference_id,
            "description": description
        }

def get_transaction_history(user_id: int, limit: int = 50):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM credit_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        return [dict(r) for r in cursor.fetchall()]
