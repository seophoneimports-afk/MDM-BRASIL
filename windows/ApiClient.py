import os
import json
import time
import base64
import hashlib
import hmac
import urllib.request
import urllib.parse
import urllib.error
from cryptography.fernet import Fernet

CONFIG_FILE = os.path.join(os.getenv("LOCALAPPDATA", "."), "MDM_FRP_BRASIL_DSM", "server_config.json")
SESSION_FILE_ENC = os.path.join(os.getenv("LOCALAPPDATA", "."), "MDM_FRP_BRASIL_DSM", "client_session.dat")
SESSION_FILE_OLD = os.path.join(os.getenv("LOCALAPPDATA", "."), "MDM_FRP_BRASIL_DSM", "client_session.json")

CREDENTIALS_FILE = os.path.join(os.getenv("LOCALAPPDATA", "."), "MDM_FRP_BRASIL_DSM", "client_creds.dat")

# Chave de integridade do cliente
CLIENT_INTEGRITY_SALT = "MDM_FRP_BRASIL_SECURE_INTEGRITY_2026_KEY"
DEFAULT_SERVER_URL = "https://mdm-brasil.onrender.com"

def _get_encryption_cipher() -> Fernet:
    # Derivação de chave de hardware (computador + usuário do windows)
    machine_id = os.environ.get("COMPUTERNAME", "PC") + ":" + os.environ.get("USERNAME", "USER") + ":" + CLIENT_INTEGRITY_SALT
    key_32 = hashlib.sha256(machine_id.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_32))

def load_server_url() -> str:
    env_url = os.getenv("MDM_CLOUD_API_URL")
    if env_url:
        return env_url.rstrip("/")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                url = cfg.get("api_url", "").strip()
                if url and "localhost" not in url and "127.0.0.1" not in url:
                    return url.rstrip("/")
        except Exception:
            pass
    local_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_config.json")
    if os.path.exists(local_cfg):
        try:
            with open(local_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                url = cfg.get("api_url", "").strip()
                if url and "localhost" not in url and "127.0.0.1" not in url:
                    return url.rstrip("/")
        except Exception:
            pass
    return DEFAULT_SERVER_URL

def save_server_url(url: str):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_url": url.rstrip("/")}, f, indent=2)

class ApiClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or load_server_url()).rstrip("/")
        self.token = None
        self.user = None
        self.official_pix = None
        self.load_session()

    def set_base_url(self, new_url: str):
        self.base_url = new_url.rstrip("/")
        save_server_url(self.base_url)

    def _request(self, method: str, path: str, data: dict = None) -> tuple[bool, dict]:
        url = f"{self.base_url}{path}"
        ts = str(int(time.time()))
        body_bytes = json.dumps(data).encode("utf-8") if data else b""
        
        # Assinatura digital HMAC para garantir integridade do EXE
        sign_payload = f"{method}:{path}:{ts}:{body_bytes.decode('utf-8') if body_bytes else ''}"
        sig = hmac.new(CLIENT_INTEGRITY_SALT.encode("utf-8"), sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MDM-FRP-Brasil-EXE/2.0-Secure",
            "X-Client-Signature": sig,
            "X-Timestamp": ts
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=body_bytes if body_bytes else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return True, resp_data
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                detail = err_data.get("detail") or err_data.get("message") or f"Erro HTTP {e.code}"
                return False, {"error": detail, "code": e.code, **(err_data if isinstance(err_data, dict) else {})}
            except Exception:
                return False, {"error": f"Erro HTTP {e.code}: {e.reason}", "code": e.code}
        except Exception as e:
            return False, {"error": f"Falha de conexão com a API Cloud: {str(e)}"}

    def is_logged_in(self) -> bool:
        return bool(self.token and self.user)

    def login(self, email: str, password: str) -> tuple[bool, str]:
        ok, res = self._request("POST", "/api/v1/exe/auth/login", {"email": email, "password": password})
        if ok and res.get("success"):
            self.token = res.get("token")
            self.user = res.get("user")
            self.save_session()
            self.fetch_official_pix_config()
            return True, "Login realizado com sucesso!"
        return False, res.get("error", "Falha na autenticação.")

    def get_balance(self) -> tuple[bool, int, str]:
        if not self.token:
            return False, 0, "Usuário não autenticado."
        ok, res = self._request("GET", "/api/v1/exe/wallet/balance")
        if ok and res.get("success"):
            bal = res.get("balance_credits", 0)
            if self.user:
                self.user["balance_credits"] = bal
                self.save_session()
            return True, bal, "Saldo obtido com sucesso."
        return False, 0, res.get("error", "Erro ao obter saldo.")

    def fetch_official_pix_config(self) -> tuple[bool, dict]:
        if not self.token:
            return False, {}
        ok, res = self._request("GET", "/api/v1/exe/pix/config")
        if ok and res.get("success"):
            self.official_pix = res
            return True, res
        return False, {}

    def create_pix_recharge(self, credits_amount: int) -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login na sua conta para recarregar."}
        return self._request("POST", "/api/v1/client/pix/create", {"credits_amount": credits_amount})

    def check_pix_status(self, txid: str) -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login na sua conta."}
        return self._request("GET", f"/api/v1/client/pix/status/{txid}")

    def consume_credit(self, device_serial: str, device_model: str, client_name: str = "Cliente", service_name: str = "MDM/FRP") -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login na sua conta para consumir créditos."}

        payload = {
            "device_serial": device_serial,
            "device_model": device_model,
            "service_code": "FRP_MDM_UNLOCK",
            "service_name": service_name,
            "client_name": client_name,
            "credits_to_consume": 1
        }
        ok, res = self._request("POST", "/api/v1/exe/services/consume", payload)
        if ok and res.get("authorized"):
            new_bal = res.get("new_balance", 0)
            if self.user:
                self.user["balance_credits"] = new_bal
                self.save_session()
            return True, res
        return False, res

    def save_custom_pix(self, pix_key: str, merchant_name: str, merchant_city: str, key_type: str = "AUTO") -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login na sua conta para salvar a chave PIX."}
        payload = {
            "pix_key": pix_key.strip(),
            "key_type": key_type.strip().upper(),
            "merchant_name": merchant_name.strip(),
            "merchant_city": merchant_city.strip()
        }
        ok, res = self._request("POST", "/api/v1/client/pix-key", payload)
        if ok and res.get("success"):
            if self.user:
                self.user["custom_pix_key"] = pix_key.strip()
                self.user["custom_pix_name"] = merchant_name.strip()
                self.user["custom_pix_city"] = merchant_city.strip()
                self.user["custom_pix_type"] = key_type.strip().upper()
                self.save_session()
            return True, res
        return False, res

    def lock_device_remote(self, serial: str) -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login para comandar bloqueio remoto."}
        return self._request("POST", f"/api/v1/client/devices/{urllib.parse.quote(serial)}/lock")

    def unlock_device_remote(self, serial: str) -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login para comandar liberação remota."}
        return self._request("POST", f"/api/v1/client/devices/{urllib.parse.quote(serial)}/unlock")

    def request_device_location_remote(self, serial: str) -> tuple[bool, dict]:
        if not self.token:
            return False, {"error": "AUTH_REQUIRED", "message": "Faça login para solicitar localização remota."}
        return self._request("POST", f"/api/v1/client/devices/{urllib.parse.quote(serial)}/request-location")

    def get_client_devices(self) -> tuple[bool, list]:
        if not self.token:
            return False, []
        ok, res = self._request("GET", "/api/v1/client/devices")
        if ok and isinstance(res, list):
            return True, res
        return False, []

    def save_session(self):
        try:
            cipher = _get_encryption_cipher()
            payload = json.dumps({"token": self.token, "user": self.user, "updated_at": time.time()}).encode("utf-8")
            encrypted_data = cipher.encrypt(payload)
            os.makedirs(os.path.dirname(SESSION_FILE_ENC), exist_ok=True)
            with open(SESSION_FILE_ENC, "wb") as f:
                f.write(encrypted_data)
            # Remove arquivo sem criptografia se existir
            if os.path.exists(SESSION_FILE_OLD):
                try:
                    os.remove(SESSION_FILE_OLD)
                except Exception:
                    pass
        except Exception:
            pass

    def load_session(self):
        try:
            if os.path.exists(SESSION_FILE_ENC):
                with open(SESSION_FILE_ENC, "rb") as f:
                    encrypted_data = f.read()
                cipher = _get_encryption_cipher()
                decrypted_bytes = cipher.decrypt(encrypted_data)
                data = json.loads(decrypted_bytes.decode("utf-8"))
                self.token = data.get("token")
                self.user = data.get("user")
            elif os.path.exists(SESSION_FILE_OLD):
                with open(SESSION_FILE_OLD, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.token = data.get("token")
                    self.user = data.get("user")
                self.save_session()
        except Exception:
            self.token = None
            self.user = None

    def logout(self):
        self.token = None
        self.user = None
        self.official_pix = None
        try:
            if os.path.exists(SESSION_FILE_ENC):
                os.remove(SESSION_FILE_ENC)
            if os.path.exists(SESSION_FILE_OLD):
                os.remove(SESSION_FILE_OLD)
        except Exception:
            pass

    def save_credentials(self, email: str, password: str):
        try:
            cipher = _get_encryption_cipher()
            data = json.dumps({"email": email.strip(), "password": password, "saved_at": time.time()}).encode("utf-8")
            enc = cipher.encrypt(data)
            os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
            with open(CREDENTIALS_FILE, "wb") as f:
                f.write(enc)
        except Exception:
            pass

    def load_credentials(self) -> tuple[str, str]:
        try:
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, "rb") as f:
                    enc = f.read()
                cipher = _get_encryption_cipher()
                dec = cipher.decrypt(enc)
                data = json.loads(dec.decode("utf-8"))
                return data.get("email", ""), data.get("password", "")
        except Exception:
            pass
        return "", ""

    def clear_credentials(self):
        try:
            if os.path.exists(CREDENTIALS_FILE):
                os.remove(CREDENTIALS_FILE)
        except Exception:
            pass

