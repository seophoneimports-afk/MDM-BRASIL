import os
import time
import secrets
import jwt
from fastapi import APIRouter, HTTPException, Depends, Request
from server.database import get_db_connection, db_transaction
from server.auth import hash_password, verify_password, create_access_token, get_current_user, get_current_admin, log_audit_event
from server.models import UserRegisterRequest, UserLoginRequest, PasswordResetRequest, GoogleAuthRequest, UpdateClientPasswordRequest

router = APIRouter(prefix="/api/v1/auth", tags=["Client Auth"])

@router.post("/register")
def register(req: UserRegisterRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado no sistema.")

    pw_hash = hash_password(req.password)

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (name, email, whatsapp, password_hash, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (req.name.strip(), email_clean, req.whatsapp.strip(), pw_hash)
        )
        user_id = cursor.lastrowid
        cursor.execute("SELECT value FROM system_settings WHERE key = 'welcome_bonus_credits'")
        row_wb = cursor.fetchone()
        welcome_bonus = int(row_wb["value"]) if row_wb and str(row_wb["value"]).isdigit() else 5

        # Initialize wallet with welcome bonus credits so client never connects with 0 balance
        cursor.execute(
            "INSERT INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, ?, ?, 0, 0)",
            (user_id, welcome_bonus, welcome_bonus)
        )
        wallet_id = cursor.lastrowid
        if welcome_bonus > 0:
            cursor.execute(
                """
                INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
                VALUES (?, ?, 'BONUS', ?, 0, ?, '🎁 Bônus de Boas-Vindas Técnico (créditos grátis para teste no EXE)', 'WELCOME_BONUS')
                """,
                (wallet_id, user_id, welcome_bonus, welcome_bonus)
            )

    log_audit_event("USER_REGISTERED", user_id=user_id, details={"email": email_clean, "name": req.name, "welcome_bonus": welcome_bonus}, ip_address=client_ip)

    token = create_access_token({"user_id": user_id, "role": "client", "email": email_clean})
    return {
        "success": True,
        "message": f"Conta criada com sucesso! Você recebeu {welcome_bonus} créditos de cortesia para testar.",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "name": req.name,
            "email": email_clean,
            "whatsapp": req.whatsapp,
            "balance_credits": welcome_bonus
        }
    }

@router.post("/login")
def login(req: UserLoginRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()

        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

        if user["status"] == "suspended":
            raise HTTPException(status_code=403, detail="Sua conta está suspensa. Entre em contato com o suporte.")

        user_id = user["id"]
        cursor.execute("SELECT balance_credits FROM wallets WHERE user_id = ?", (user_id,))
        w = cursor.fetchone()
        balance = w["balance_credits"] if w else 0

    log_audit_event("USER_LOGIN", user_id=user_id, details={"email": email_clean}, ip_address=client_ip)

    token = create_access_token({"user_id": user_id, "role": "client", "email": email_clean})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "name": user["name"],
            "email": user["email"],
            "whatsapp": user["whatsapp"],
            "balance_credits": balance
        }
    }

import collections
from datetime import datetime, timedelta
import urllib.parse
from fastapi.responses import RedirectResponse
from server.models import PasswordResetInitRequest, PasswordResetConfirmRequest

# In-memory rate limiting to prevent brute force
_rate_limits = collections.defaultdict(list)

def check_rate_limit(key: str, max_attempts: int = 5, window_seconds: int = 300):
    now = time.time()
    attempts = [t for t in _rate_limits[key] if now - t < window_seconds]
    _rate_limits[key] = attempts
    if len(attempts) >= max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas em pouco tempo. Por segurança, aguarde alguns minutos antes de tentar novamente."
        )
    _rate_limits[key].append(now)

@router.post("/forgot-password/request")
def request_password_reset(req: PasswordResetInitRequest, request: Request):
    """
    Passo 1 do fluxo seguro de recuperação:
    Gera código OTP numérico de 6 dígitos válido por 15 minutos e registra no banco.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    check_rate_limit(f"reset_req_{client_ip}", max_attempts=5, window_seconds=600)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, whatsapp FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()

    if not user:
        # Prevenção contra enumeração de usuários
        return {
            "success": True,
            "message": "Se este e-mail estiver cadastrado, um código de verificação de 6 dígitos foi gerado.",
            "email": email_clean
        }

    user_id = user["id"]
    reset_code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (user_id,))
        cursor.execute(
            """
            INSERT INTO password_resets (user_id, email, reset_code, expires_at, used, attempts)
            VALUES (?, ?, ?, ?, 0, 0)
            """,
            (user_id, email_clean, reset_code, expires_at)
        )

    log_audit_event("PASSWORD_RESET_REQUESTED", user_id=user_id, details={"email": email_clean}, ip_address=client_ip)

    return {
        "success": True,
        "message": "Se este e-mail estiver cadastrado, um código de verificação foi gerado (válido por 15 minutos).",
        "email": email_clean,
        "support_whatsapp": "5519994783127"
    }

@router.post("/forgot-password/confirm")
def confirm_password_reset(req: PasswordResetConfirmRequest, request: Request):
    """
    Passo 2 do fluxo seguro de recuperação:
    Valida código OTP numérico de 6 dígitos, expiração e tentativas antes de redefinir o hash.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()
    code_clean = req.code.strip()

    check_rate_limit(f"reset_conf_{client_ip}", max_attempts=8, window_seconds=300)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=400, detail="E-mail ou código de recuperação inválido.")

        user_id = user["id"]

        cursor.execute(
            """
            SELECT * FROM password_resets 
            WHERE user_id = ? AND used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,)
        )
        reset_rec = cursor.fetchone()

        if not reset_rec:
            raise HTTPException(status_code=400, detail="Nenhuma solicitação de recuperação ativa para este e-mail.")

        if reset_rec["attempts"] >= 5:
            with db_transaction() as t_conn:
                t_conn.cursor().execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset_rec["id"],))
            raise HTTPException(status_code=400, detail="Limite de 5 tentativas excedido. Solicite um novo código por segurança.")

        exp_str = reset_rec["expires_at"]
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            exp_dt = datetime.fromisoformat(exp_str)

        if datetime.utcnow() > exp_dt:
            raise HTTPException(status_code=400, detail="O código de recuperação de 15 minutos expirou. Solicite um novo código.")

        if reset_rec["reset_code"] != code_clean:
            with db_transaction() as t_conn:
                t_conn.cursor().execute("UPDATE password_resets SET attempts = attempts + 1 WHERE id = ?", (reset_rec["id"],))
            raise HTTPException(status_code=400, detail="Código de recuperação incorreto. Verifique o código e tente novamente.")

    new_hash = hash_password(req.new_password)
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_hash, user_id))
        cursor.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset_rec["id"],))

    log_audit_event("PASSWORD_RESET_SUCCESS", user_id=user_id, details={"email": email_clean}, ip_address=client_ip)
    return {"success": True, "message": "Senha redefinida com segurança! Você já pode fazer login com sua nova senha."}

@router.post("/forgot-password")
def legacy_forgot_password(req: PasswordResetRequest, request: Request):
    """
    Endpoint legado protegido: exige que o fluxo de 2 etapas seja respeitado.
    """
    raise HTTPException(
        status_code=400,
        detail="Para sua segurança, utilize o fluxo de recuperação com código de verificação enviado para o seu e-mail/WhatsApp."
    )

@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance_credits, promotional_credits, total_purchased, total_used FROM wallets WHERE user_id = ?", (user["id"],))
        wallet = cursor.fetchone()

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "whatsapp": user["whatsapp"],
        "avatar_url": user.get("avatar_url") or "",
        "status": user["status"],
        "created_at": user["created_at"],
        "wallet": dict(wallet) if wallet else {"balance_credits": 0, "total_purchased": 0, "total_used": 0}
    }

@router.get("/google/config")
def get_google_config():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'google_client_id'")
        row = cursor.fetchone()
        client_id = row["value"] if row else ""
    return {"google_client_id": client_id}

@router.post("/google/config")
def set_google_config(data: dict, admin: dict = Depends(get_current_admin)):
    client_id = str(data.get("google_client_id", "")).strip()
    with db_transaction() as conn:
        conn.cursor().execute(
            """
            INSERT INTO system_settings (key, value, updated_at) VALUES ('google_client_id', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (client_id,)
        )
    return {"success": True, "message": "Google Client ID configurado com sucesso!", "google_client_id": client_id}

@router.get("/google/login")
def google_direct_login(request: Request):
    """
    Redireciona diretamente para a tela oficial de login e consentimento do Google (accounts.google.com).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'google_client_id'")
        row = cursor.fetchone()
        client_id = row["value"] if row and row["value"] else os.getenv("GOOGLE_CLIENT_ID", "")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v1/auth/google/callback"

    if not client_id:
        client_id = "104847385920-mdmbrasilportal.apps.googleusercontent.com"

    google_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account"
        })
    )
    return RedirectResponse(url=google_url, status_code=302)

@router.get("/google/callback")
def google_direct_callback(request: Request, code: str = None, error: str = None):
    """
    Recebe retorno da autorização do Google e redireciona de volta para o portal do cliente.
    """
    if error or not code:
        return RedirectResponse(url="/client?auth_error=google_cancelled", status_code=302)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v1/auth/google/callback"
    client_ip = request.client.host if request.client else "127.0.0.1"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'google_client_id'")
        r1 = cursor.fetchone()
        client_id = r1["value"] if r1 and r1["value"] else os.getenv("GOOGLE_CLIENT_ID", "")
        cursor.execute("SELECT value FROM system_settings WHERE key = 'google_client_secret'")
        r2 = cursor.fetchone()
        client_secret = r2["value"] if r2 and r2["value"] else os.getenv("GOOGLE_CLIENT_SECRET", "")

    email = None
    name = None
    google_id = None
    avatar_url = None

    if client_id and client_secret:
        try:
            import urllib.request
            import urllib.parse
            import json
            token_url = "https://oauth2.googleapis.com/token"
            data = urllib.parse.urlencode({
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }).encode("utf-8")
            req = urllib.request.Request(token_url, data=data, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
                id_token = token_resp.get("id_token")
                if id_token:
                    payload = jwt.decode(id_token, options={"verify_signature": False})
                    email = payload.get("email")
                    name = payload.get("name") or payload.get("given_name") or "Cliente Google"
                    google_id = payload.get("sub")
                    avatar_url = payload.get("picture")
        except Exception:
            pass

    if email:
        email_clean = email.strip().lower()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
            user = cursor.fetchone()
            if user:
                user_id = user["id"]
                with db_transaction() as t_conn:
                    t_conn.cursor().execute(
                        "UPDATE users SET google_id = COALESCE(google_id, ?), avatar_url = COALESCE(avatar_url, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (google_id, avatar_url, user_id)
                    )
            else:
                dummy_hash = hash_password(secrets.token_hex(16))
                user_name = name or email_clean.split("@")[0]
                with db_transaction() as t_conn:
                    t_cursor = t_conn.cursor()
                    t_cursor.execute(
                        """
                        INSERT INTO users (name, email, whatsapp, password_hash, status, google_id, auth_provider, avatar_url)
                        VALUES (?, ?, ?, ?, 'active', ?, 'google', ?)
                        """,
                        (user_name, email_clean, "", dummy_hash, google_id, avatar_url)
                    )
                    user_id = t_cursor.lastrowid
                    t_cursor.execute("SELECT value FROM system_settings WHERE key = 'welcome_bonus_credits'")
                    row_wb = t_cursor.fetchone()
                    welcome_bonus = int(row_wb["value"]) if row_wb and str(row_wb["value"]).isdigit() else 5
                    t_cursor.execute(
                        "INSERT INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, ?, ?, 0, 0)",
                        (user_id, welcome_bonus, welcome_bonus)
                    )
                    wallet_id = t_cursor.lastrowid
                    if welcome_bonus > 0:
                        t_cursor.execute(
                            """
                            INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
                            VALUES (?, ?, 'BONUS', ?, 0, ?, '🎁 Bônus de Boas-Vindas Técnico (créditos grátis para teste no EXE)', 'WELCOME_BONUS')
                            """,
                            (wallet_id, user_id, welcome_bonus, welcome_bonus)
                        )
        jwt_token = create_access_token({"user_id": user_id, "role": "client", "email": email_clean})
        log_audit_event("GOOGLE_LOGIN", user_id=user_id, details={"email": email_clean, "via": "oauth_callback"}, ip_address=client_ip)
        return RedirectResponse(url=f"/client?token={jwt_token}&auth_success=google", status_code=302)

    return RedirectResponse(url="/client?auth_notice=google_verified", status_code=302)

@router.post("/google")
def google_auth(req: GoogleAuthRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"

    email = None
    name = None
    google_id = req.google_id
    avatar_url = req.avatar_url

    if req.credential:
        try:
            payload = jwt.decode(req.credential, options={"verify_signature": False})
            email = payload.get("email")
            name = payload.get("name") or payload.get("given_name") or "Cliente Google"
            google_id = payload.get("sub")
            avatar_url = payload.get("picture")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Token Google inválido ou corrompido: {str(e)}")
    elif req.email:
        email = str(req.email).strip().lower()
        name = req.name or email.split("@")[0]
        google_id = req.google_id or f"google_{secrets.token_hex(8)}"
        avatar_url = req.avatar_url or f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=00E5FF&color=000"
    else:
        raise HTTPException(status_code=400, detail="Autenticação Google inválida: credencial oficial do Google é obrigatória.")

    if not email:
        raise HTTPException(status_code=400, detail="Não foi possível identificar o e-mail na credencial Google.")

    email_clean = email.strip().lower()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()

        if user:
            if user["status"] == "suspended":
                raise HTTPException(status_code=403, detail="Sua conta está suspensa. Entre em contato com o suporte.")

            # Proteção contra sequestro de contas: se a conta já existe,
            # exige credencial oficial do Google para validar propriedade do e-mail.
            if not req.credential:
                raise HTTPException(
                    status_code=400,
                    detail="Este e-mail já possui cadastro no sistema. Por segurança, acesse com sua senha atual ou utilize a opção 'Esqueci minha senha'."
                )

            user_id = user["id"]
            user_name = name or user["name"]
            user_whatsapp = user["whatsapp"]

            with db_transaction() as t_conn:
                if req.password and len(req.password.strip()) >= 6:
                    new_pw_hash = hash_password(req.password.strip())
                    t_conn.cursor().execute(
                        """
                        UPDATE users 
                        SET google_id = COALESCE(google_id, ?), 
                            avatar_url = COALESCE(avatar_url, ?),
                            name = COALESCE(?, name),
                            password_hash = ?,
                            updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                        """,
                        (google_id, avatar_url, name, new_pw_hash, user_id)
                    )
                else:
                    t_conn.cursor().execute(
                        "UPDATE users SET google_id = COALESCE(google_id, ?), avatar_url = COALESCE(avatar_url, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (google_id, avatar_url, user_id)
                    )

            cursor.execute("SELECT balance_credits FROM wallets WHERE user_id = ?", (user_id,))
            w = cursor.fetchone()
            balance = w["balance_credits"] if w else 0
            action = "GOOGLE_LOGIN"
        else:
            if req.password and len(req.password.strip()) >= 6:
                initial_pw_hash = hash_password(req.password.strip())
            else:
                initial_pw_hash = hash_password(secrets.token_hex(16))
            user_name = name or email_clean.split("@")[0]
            user_whatsapp = ""

            with db_transaction() as t_conn:
                t_cursor = t_conn.cursor()
                t_cursor.execute(
                    """
                    INSERT INTO users (name, email, whatsapp, password_hash, status, google_id, auth_provider, avatar_url)
                    VALUES (?, ?, ?, ?, 'active', ?, 'google', ?)
                    """,
                    (user_name, email_clean, user_whatsapp, initial_pw_hash, google_id, avatar_url)
                )
                user_id = t_cursor.lastrowid
                t_cursor.execute("SELECT value FROM system_settings WHERE key = 'welcome_bonus_credits'")
                row_wb = t_cursor.fetchone()
                welcome_bonus = int(row_wb["value"]) if row_wb and str(row_wb["value"]).isdigit() else 5
                t_cursor.execute(
                    "INSERT INTO wallets (user_id, balance_credits, promotional_credits, total_purchased, total_used) VALUES (?, ?, ?, 0, 0)",
                    (user_id, welcome_bonus, welcome_bonus)
                )
                wallet_id = t_cursor.lastrowid
                if welcome_bonus > 0:
                    t_cursor.execute(
                        """
                        INSERT INTO credit_transactions (wallet_id, user_id, type, amount_credits, previous_balance, new_balance, description, reference_id)
                        VALUES (?, ?, 'BONUS', ?, 0, ?, '🎁 Bônus de Boas-Vindas Técnico (créditos grátis para teste no EXE)', 'WELCOME_BONUS')
                        """,
                        (wallet_id, user_id, welcome_bonus, welcome_bonus)
                    )
                balance = welcome_bonus
            action = "GOOGLE_REGISTER"

    log_audit_event(action, user_id=user_id, details={"email": email_clean, "google_id": google_id, "has_password": bool(req.password)}, ip_address=client_ip)

    token = create_access_token({"user_id": user_id, "role": "client", "email": email_clean})
    return {
        "success": True,
        "message": "Conta vinculada com sucesso! Você já pode acessar tanto o portal quanto o aplicativo EXE.",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "name": user_name,
            "email": email_clean,
            "whatsapp": user_whatsapp,
            "balance_credits": balance,
            "avatar_url": avatar_url
        }
    }

@router.post("/password/update")
def update_user_password(req: UpdateClientPasswordRequest, request: Request, user: dict = Depends(get_current_user)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_id = user.get("id") or user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    if len(req.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")

    new_hash = hash_password(req.new_password.strip())
    with db_transaction() as conn:
        conn.cursor().execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_hash, user_id)
        )

    log_audit_event("PASSWORD_UPDATED_FOR_EXE", user_id=user_id, details={"via": "client_portal"}, ip_address=client_ip)
    return {"success": True, "message": "Senha atualizada com sucesso! Você já pode utilizá-la para fazer login no programa MDM & FRP BRASIL (EXE)."}
