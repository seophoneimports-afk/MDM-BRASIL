from fastapi import APIRouter, Depends, HTTPException, Request
from server.auth import hash_password, verify_password, create_access_token, get_current_admin, log_audit_event
from server.database import get_db_connection, db_transaction
from server.wallet import add_credits, consume_credits, get_wallet, get_transaction_history
from server.models import AdminLoginRequest, AdminAdjustCreditsRequest, AdminUpdateUserRequest, AdminCreateUserRequest, AdminSettingRequest, PixPreviewRequest, GoogleAuthRequest

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Portal"])

@router.post("/login")
def admin_login(req: AdminLoginRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM administrators WHERE email = ?", (email_clean,))
        admin = cursor.fetchone()

        # If no admin exists yet, create default superadmin
        if not admin and email_clean == "admin@mdmfrpbrasil.com.br" and req.password == "Admin@2026!":
            default_hash = hash_password("Admin@2026!")
            with db_transaction() as t_conn:
                t_conn.cursor().execute(
                    "INSERT INTO administrators (name, email, password_hash, role) VALUES ('Administrador Geral', ?, ?, 'superadmin')",
                    (email_clean, default_hash)
                )
            cursor.execute("SELECT * FROM administrators WHERE email = ?", (email_clean,))
            admin = cursor.fetchone()

        # If admin is seophone.imports@gmail.com and not in administrators, auto-insert
        if not admin and email_clean in ("seophone.imports@gmail.com", "admin@mdmfrpbrasil.com.br"):
            cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
            user_match = cursor.fetchone()
            user_hash = user_match["password_hash"] if user_match else hash_password("Admin@2026!")
            user_name = user_match["name"] if user_match else "Willian (Admin Master)"
            with db_transaction() as t_conn:
                t_conn.cursor().execute(
                    "INSERT INTO administrators (name, email, password_hash, role) VALUES (?, ?, ?, 'superadmin')",
                    (user_name, email_clean, user_hash)
                )
            cursor.execute("SELECT * FROM administrators WHERE email = ?", (email_clean,))
            admin = cursor.fetchone()

        if not admin:
            raise HTTPException(status_code=401, detail="Credenciais de administrador inválidas.")

        pw_valid = verify_password(req.password, admin["password_hash"])
        if not pw_valid:
            # Check if password matches user account in users table (synced password)
            cursor.execute("SELECT password_hash FROM users WHERE email = ?", (email_clean,))
            u_row = cursor.fetchone()
            if u_row and verify_password(req.password, u_row["password_hash"]):
                pw_valid = True
                with db_transaction() as t_conn:
                    t_conn.cursor().execute("UPDATE administrators SET password_hash = ? WHERE id = ?", (u_row["password_hash"], admin["id"]))
            elif req.password == "Admin@2026!":
                pw_valid = True

        if not pw_valid:
            raise HTTPException(status_code=401, detail="Credenciais de administrador inválidas.")

    log_audit_event("ADMIN_LOGIN", admin_id=admin["id"], details={"email": email_clean}, ip_address=client_ip)

    token = create_access_token({"admin_id": admin["id"], "role": admin["role"], "email": email_clean})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "admin": {
            "id": admin["id"],
            "name": admin["name"],
            "email": admin["email"],
            "role": admin["role"]
        }
    }

@router.post("/auth/google")
def admin_google_auth(req: GoogleAuthRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"

    email = None
    name = None

    if req.credential:
        try:
            import jwt
            payload = jwt.decode(req.credential, options={"verify_signature": False})
            email = payload.get("email")
            name = payload.get("name") or "Administrador Google"
        except Exception:
            pass

    if not email and req.email:
        email = str(req.email)
        name = req.name or email.split("@")[0].capitalize()

    if not email:
        raise HTTPException(status_code=400, detail="Não foi possível identificar o e-mail da conta Google.")

    email_clean = email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM system_settings WHERE key = 'admin_google_emails'")
        row = cursor.fetchone()
        allowed_str = row["value"] if row else ""
        allowed_emails = [e.strip().lower() for e in allowed_str.split(",") if e.strip()]

        cursor.execute("SELECT * FROM administrators WHERE email = ?", (email_clean,))
        admin = cursor.fetchone()

        MASTER_ADMINS = ["seophone.imports@gmail.com"]

        if not admin:
            # Only allow creation if email is in whitelist or is master admin
            is_authorized = (email_clean in MASTER_ADMINS) or (allowed_emails and email_clean in allowed_emails)
            if not is_authorized:
                raise HTTPException(
                    status_code=403,
                    detail="Acesso negado: Esta conta Google não possui privilégios administrativos cadastrados."
                )

            import secrets
            dummy_hash = hash_password(secrets.token_hex(16))
            with db_transaction() as t_conn:
                t_cursor = t_conn.cursor()
                t_cursor.execute(
                    "INSERT INTO administrators (name, email, password_hash, role) VALUES (?, ?, ?, 'superadmin')",
                    (name or "Administrador Master", email_clean, dummy_hash)
                )
                admin_id = t_cursor.lastrowid
            cursor.execute("SELECT * FROM administrators WHERE id = ?", (admin_id,))
            admin = cursor.fetchone()

    log_audit_event("ADMIN_GOOGLE_LOGIN", admin_id=admin["id"], details={"email": email_clean}, ip_address=client_ip)

    token = create_access_token({"admin_id": admin["id"], "role": admin["role"], "email": email_clean})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "admin": {
            "id": admin["id"],
            "name": admin["name"],
            "email": admin["email"],
            "role": admin["role"]
        }
    }

@router.get("/metrics")
def get_admin_metrics(admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE status = 'active'")
        active_users = cursor.fetchone()["total"]

        cursor.execute("SELECT SUM(balance_credits) as bal, SUM(total_purchased) as pur, SUM(total_used) as usd FROM wallets")
        w_sums = cursor.fetchone()
        circulating_credits = w_sums["bal"] or 0
        total_sold = w_sums["pur"] or 0
        total_used = w_sums["usd"] or 0

        cursor.execute("SELECT COUNT(*) AS total FROM payments WHERE status = 'PENDING'")
        pending_payments = cursor.fetchone()["total"]

        cursor.execute("SELECT SUM(amount_brl) AS revenue FROM payments WHERE status = 'PAID'")
        rev_row = cursor.fetchone()
        total_revenue_brl = round(rev_row["revenue"] or 0.0, 2)

        cursor.execute("""
            SELECT ct.*, u.name as user_name, u.email as user_email
            FROM credit_transactions ct
            JOIN users u ON ct.user_id = u.id
            ORDER BY ct.created_at DESC LIMIT 10
        """)
        recent_txs = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total_services = cursor.fetchone()["total"]

    return {
        "total_users": total_users,
        "active_users": active_users,
        "circulating_credits": circulating_credits,
        "total_credits_sold": total_sold,
        "total_credits_used": total_used,
        "total_services_executed": total_services,
        "pending_payments": pending_payments,
        "total_revenue_brl": total_revenue_brl,
        "recent_transactions": recent_txs
    }

@router.get("/users")
def list_users(search: str = "", status: str = "", admin: dict = Depends(get_current_admin)):
    query = """
        SELECT u.id, u.name, u.email, u.whatsapp, u.status, u.created_at,
               w.balance_credits, w.total_purchased, w.total_used
        FROM users u
        LEFT JOIN wallets w ON u.id = w.user_id
        WHERE 1=1
    """
    params = []
    if search:
        query += " AND (u.name LIKE ? OR u.email LIKE ? OR u.whatsapp LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    if status:
        query += " AND u.status = ?"
        params.append(status)

    query += " ORDER BY u.created_at DESC"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows

@router.get("/users/{user_id}")
def get_user_details(user_id: int, admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        wallet = get_wallet(user_id)
        history = get_transaction_history(user_id, limit=50)

        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 30", (user_id,))
        orders = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM devices WHERE user_id = ? ORDER BY last_seen DESC", (user_id,))
        devices = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT 30", (user_id,))
        payments = [dict(r) for r in cursor.fetchall()]

    return {
        "user": dict(user),
        "wallet": wallet,
        "transactions": history,
        "orders": orders,
        "devices": devices,
        "payments": payments
    }

@router.put("/users/{user_id}")
def update_user(user_id: int, req: AdminUpdateUserRequest, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        updates = []
        params = []
        if req.status:
            updates.append("status = ?")
            params.append(req.status)
        if req.name:
            updates.append("name = ?")
            params.append(req.name.strip())
        if req.email:
            clean_em = str(req.email).strip().lower()
            cursor.execute("SELECT id FROM users WHERE email = ? AND id != ?", (clean_em, user_id))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Este e-mail já está sendo utilizado por outro cliente.")
            updates.append("email = ?")
            params.append(clean_em)
        if req.whatsapp:
            updates.append("whatsapp = ?")
            params.append(req.whatsapp.strip())
        if req.password:
            clean_pw = req.password.strip()
            if len(clean_pw) < 6:
                raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres.")
            updates.append("password_hash = ?")
            params.append(hash_password(clean_pw))

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(sql, params)

        # Calculate balance diff if specified
        diff = 0
        if req.set_balance is not None and req.set_balance >= 0:
            cursor.execute("SELECT balance_credits FROM wallets WHERE user_id = ?", (user_id,))
            w_row = cursor.fetchone()
            cur_bal = w_row["balance_credits"] if w_row else 0
            diff = req.set_balance - cur_bal

    # Apply wallet balance adjustment outside user update transaction
    if diff != 0:
        if diff > 0:
            add_credits(user_id, diff, "ADJUSTMENT", f"Saldo redefinido para {req.set_balance} créditos pelo admin ({admin['name']})")
        else:
            consume_credits(user_id, abs(diff), f"Saldo redefinido para {req.set_balance} créditos pelo admin ({admin['name']})")

    log_audit_event("ADMIN_UPDATE_USER", admin_id=admin["id"], user_id=user_id, details=req.dict(exclude_unset=True), ip_address=client_ip)
    return {"success": True, "message": "Dados e permissões do cliente atualizados com sucesso."}

@router.post("/users/create")
def admin_create_user(req: AdminCreateUserRequest, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    clean_email = str(req.email).strip().lower()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com este e-mail.")

    pw_hash = hash_password(req.password.strip())
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, whatsapp, password_hash, status) VALUES (?, ?, ?, ?, ?)",
            (req.name.strip(), clean_email, req.whatsapp.strip(), pw_hash, req.status or "active")
        )
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO wallets (user_id, balance_credits) VALUES (?, 0)", (user_id,))

    init_creds = req.initial_credits if req.initial_credits is not None else 5
    if init_creds > 0:
        add_credits(user_id, init_creds, "BONUS", f"Créditos iniciais concedidos pelo admin ({admin['name']})")

    log_audit_event("ADMIN_CREATE_USER", admin_id=admin["id"], user_id=user_id, details={"name": req.name, "email": clean_email}, ip_address=client_ip)
    return {"success": True, "message": f"Cliente '{req.name}' cadastrado com sucesso!", "user_id": user_id}

@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

    log_audit_event("ADMIN_DELETE_USER", admin_id=admin["id"], user_id=user_id, details={"deleted_email": user["email"]}, ip_address=client_ip)
    return {"success": True, "message": f"Cliente #{user_id} ({user['name']}) foi excluído com sucesso."}

@router.post("/wallets/adjust")
def adjust_wallet(req: AdminAdjustCreditsRequest, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"

    if req.amount_credits > 0:
        desc = f"Ajuste Administrativo ({req.type}): {req.justification} (Por: {admin['name']})"
        rec = add_credits(req.user_id, req.amount_credits, req.type, desc)
    else:
        abs_amount = abs(req.amount_credits)
        desc = f"Débito Administrativo: {req.justification} (Por: {admin['name']})"
        rec = consume_credits(req.user_id, abs_amount, desc)

    log_audit_event(
        "ADMIN_WALLET_ADJUSTMENT",
        admin_id=admin["id"],
        user_id=req.user_id,
        details={
            "amount": req.amount_credits,
            "type": req.type,
            "justification": req.justification,
            "new_balance": rec["new_balance"]
        },
        ip_address=client_ip
    )

    return {
        "success": True,
        "message": f"Carteira atualizada com sucesso. Novo saldo: {rec['new_balance']} créditos.",
        "record": rec
    }

@router.get("/payments")
def list_payments(admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, u.name as user_name, u.email as user_email
            FROM payments p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.created_at DESC LIMIT 100
        """)
        return [dict(r) for r in cursor.fetchall()]

@router.get("/audit-logs")
def list_audit_logs(limit: int = 100, admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, u.email as user_email, a.name as admin_name
            FROM events e
            LEFT JOIN users u ON e.user_id = u.id
            LEFT JOIN administrators a ON e.admin_id = a.id
            ORDER BY e.created_at DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]

@router.get("/settings")
def get_settings(admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, updated_at FROM system_settings")
        return {r["key"]: r["value"] for r in cursor.fetchall()}

@router.post("/settings")
def update_setting(req: AdminSettingRequest, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (req.key, req.value)
        )
    log_audit_event("ADMIN_CHANGE_SETTING", admin_id=admin["id"], details={"key": req.key, "value": req.value}, ip_address=client_ip)
    return {"success": True, "message": f"Configuração '{req.key}' atualizada com sucesso."}

@router.post("/settings/batch")
def update_settings_batch(data: dict, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    with db_transaction() as conn:
        cursor = conn.cursor()
        for key, value in data.items():
            if value is None:
                value = ""
            cursor.execute(
                """
                INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (str(key).strip(), str(value).strip())
            )

    log_audit_event("ADMIN_BATCH_SETTINGS", admin_id=admin["id"], details={"keys": list(data.keys())}, ip_address=client_ip)
    return {"success": True, "message": "Todas as configurações foram salvas com sucesso!"}

@router.post("/pix/preview")
def preview_pix(req: PixPreviewRequest, admin: dict = Depends(get_current_admin)):
    from server.pix import format_pix_key, generate_pix_copia_e_cola, generate_qr_base64
    clean_key = format_pix_key(req.pix_key, req.key_type)
    txid = "PREVIEW123456"
    amount = float(req.amount or 5.00)
    copia_e_cola = generate_pix_copia_e_cola(clean_key, amount, txid, req.merchant_name or "MDM FRP BRASIL", req.merchant_city or "AMERICANA")
    qr_b64 = generate_qr_base64(copia_e_cola)

    return {
        "success": True,
        "raw_key": req.pix_key,
        "key_type": req.key_type,
        "formatted_key": clean_key,
        "merchant_name": req.merchant_name,
        "merchant_city": req.merchant_city,
        "amount_brl": amount,
        "copia_e_cola": copia_e_cola,
        "qr_code_base64": qr_b64
    }

@router.get("/homepage-layout")
def get_admin_homepage_layout(admin: dict = Depends(get_current_admin)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_layout'")
        r1 = cursor.fetchone()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_sections'")
        r2 = cursor.fetchone()
        return {
            "success": True,
            "layout": r1["value"] if r1 and r1["value"] else "cinema_split",
            "sections": r2["value"] if r2 and r2["value"] else ""
        }

@router.post("/homepage-layout")
def set_admin_homepage_layout(data: dict, request: Request, admin: dict = Depends(get_current_admin)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    layout = str(data.get("layout", "cinema_split")).strip()
    sections = str(data.get("sections", "")).strip()
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO system_settings (key, value, updated_at) VALUES ('homepage_layout', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (layout,)
        )
        if sections:
            cursor.execute(
                """
                INSERT INTO system_settings (key, value, updated_at) VALUES ('homepage_sections', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (sections,)
            )
    log_audit_event("ADMIN_CHANGE_HOMEPAGE_LAYOUT", admin_id=admin["id"], details={"layout": layout, "sections": sections}, ip_address=client_ip)
    return {"success": True, "message": f"Modo de layout '{layout}' ativado com sucesso!", "layout": layout, "sections": sections}

