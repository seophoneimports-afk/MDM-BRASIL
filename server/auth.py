import os
import time
import json
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from server.database import get_db_connection, db_transaction

SECRET_KEY = os.getenv("MDM_JWT_SECRET", "mdm_frp_brasil_super_secret_jwt_key_2026_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days

security_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Por favor, faça login novamente."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação inválido."
        )

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security_bearer)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária. Cabeçalho Authorization ausente."
        )
    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("user_id")
    role = payload.get("role", "client")

    if not user_id or role != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado para esta conta."
        )

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        if user["status"] == "suspended":
            raise HTTPException(status_code=403, detail="Sua conta foi suspensa pela administração.")
        return dict(user)

def get_current_admin(credentials: HTTPAuthorizationCredentials = Security(security_bearer)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação administrativa necessária."
        )
    token = credentials.credentials
    payload = decode_token(token)
    admin_id = payload.get("admin_id")
    role = payload.get("role")

    if not admin_id or role not in ("superadmin", "support"):
        # Check if user email is a registered administrator (SSO)
        email = payload.get("email")
        if email:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM administrators WHERE email = ?", (email.strip().lower(),))
                admin = cursor.fetchone()
                if admin:
                    return dict(admin)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao Painel Administrativo."
        )

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM administrators WHERE id = ?", (admin_id,))
        admin = cursor.fetchone()
        if not admin:
            raise HTTPException(status_code=404, detail="Administrador não encontrado.")
        return dict(admin)

def log_audit_event(event_type: str, user_id: int = None, admin_id: int = None, details: dict = None, ip_address: str = "127.0.0.1"):
    try:
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (user_id, admin_id, event_type, details_json, ip_address) VALUES (?, ?, ?, ?, ?)",
                (user_id, admin_id, event_type, json.dumps(details or {}, ensure_ascii=False), ip_address)
            )
    except Exception as e:
        print(f"[AUDIT LOG ERROR] Failed to record event {event_type}: {e}")
