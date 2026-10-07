import os
import sys
import subprocess
import shutil
import json
import logging
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import urllib.request

logger = logging.getLogger("AdbManager")

BACKEND_STATE_FILE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MDM_FRP_BRASIL_DSM", "backend_state.json")

class BackendStateStore:
    """
    Authoritative backend state store.
    Persists device states: PENDING, AUTHORIZED, PROCESSING, COMPLETED.
    """
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.state_file = BACKEND_STATE_FILE
        self.devices = {}
        self.operations = {}
        self.device_locations = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.devices = data.get("devices", {})
                    self.operations = data.get("operations", {})
                    self.device_locations = data.get("locations", {})
        except Exception as e:
            logger.warning(f"Could not load backend state file: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"devices": self.devices, "operations": self.operations, "locations": self.device_locations}, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save backend state file: {e}")

    def get_device_state(self, device_id):
        with self._lock:
            return self.devices.get(device_id, {
                "deviceId": device_id,
                "status": "PENDING",
                "operationId": f"OP-{datetime.now().strftime('%Y%m%d')}-001",
                "updatedAt": int(time.time() * 1000)
            })

    def set_device_pending(self, device_id, model, client, service, val, pix):
        with self._lock:
            op_id = f"OP-{datetime.now().strftime('%Y%m%d%H%M')}"
            rec = {
                "deviceId": device_id,
                "model": model,
                "status": "PENDING",
                "operationId": op_id,
                "client": client,
                "service": service,
                "value": val,
                "pix": pix,
                "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": int(time.time() * 1000)
            }
            self.devices[device_id] = rec
            self.operations[op_id] = rec
            self._save()
            return rec

    def authorize_device(self, device_id, model=None, authorized_by="ADMIN_EXE"):
        with self._lock:
            existing = self.devices.get(device_id, {})
            # Idempotency check: if already authorized with valid operationId, keep it
            op_id = existing.get("operationId")
            if not op_id or op_id == "N/A":
                op_id = f"OP-{datetime.now().strftime('%Y%m%d%H%M')}"

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_ms = int(time.time() * 1000)

            rec = {
                "deviceId": device_id,
                "model": model or existing.get("model", "Android Device"),
                "status": "AUTHORIZED",
                "operationId": op_id,
                "client": existing.get("client", "Cliente Autorizado"),
                "service": existing.get("service", "Serviço Técnico"),
                "value": existing.get("value", "R$ 250,00"),
                "pix": existing.get("pix", "19994783127"),
                "authorizedBy": authorized_by,
                "authorizedAt": now_str,
                "updatedAt": now_ms
            }
            self.devices[device_id] = rec
            self.operations[op_id] = rec
            self._save()
            return rec

    def set_device_processing(self, device_id):
        with self._lock:
            if device_id in self.devices:
                self.devices[device_id]["status"] = "PROCESSING"
                self.devices[device_id]["updatedAt"] = int(time.time() * 1000)
                self._save()

    def set_device_completed(self, device_id, op_id=None):
        with self._lock:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_ms = int(time.time() * 1000)
            if device_id in self.devices:
                self.devices[device_id]["status"] = "COMPLETED"
                self.devices[device_id]["completedAt"] = now_str
                self.devices[device_id]["updatedAt"] = now_ms
            if op_id and op_id in self.operations:
                self.operations[op_id]["status"] = "COMPLETED"
                self.operations[op_id]["completedAt"] = now_str
            self._save()

    def update_device_location(self, device_id, location_data):
        with self._lock:
            if device_id not in self.device_locations:
                self.device_locations[device_id] = {
                    "current": None,
                    "history": []
                }

            # Enriquecer com endereço reverso caso não fornecido pelo aparelho
            lat = location_data.get("latitude")
            lon = location_data.get("longitude")
            if (not location_data.get("street") or not location_data.get("neighborhood")) and lat is not None and lon is not None:
                geo = reverse_geocode_address(float(lat), float(lon))
                for k, v in geo.items():
                    if v and not location_data.get(k):
                        location_data[k] = v

            self.device_locations[device_id]["current"] = location_data
            history = self.device_locations[device_id].setdefault("history", [])
            history.insert(0, location_data)
            # Limit history to 100 entries
            if len(history) > 100:
                self.device_locations[device_id]["history"] = history[:100]

            # Também espelhar para os seriais cadastrados em devices para consulta instantânea
            for s_id in list(self.devices.keys()):
                if s_id != device_id:
                    if s_id not in self.device_locations:
                        self.device_locations[s_id] = {"current": None, "history": []}
                    self.device_locations[s_id]["current"] = location_data

            self._save()
            return location_data

    def get_device_location(self, device_id):
        with self._lock:
            # 1. Correspondência exata
            if device_id in self.device_locations:
                loc = self.device_locations[device_id]
                if loc and loc.get("current") and loc["current"].get("latitude") is not None:
                    return loc
            # 2. Correspondência parcial (ex: serial vs android_id)
            for did, rec in self.device_locations.items():
                if device_id in did or did in str(device_id):
                    if rec and rec.get("current") and rec["current"].get("latitude") is not None:
                        return rec
            # 3. Retornar o registro mais recente que possua coordenadas válidas
            best_rec = None
            best_ts = 0
            for did, rec in self.device_locations.items():
                cur = rec.get("current") if isinstance(rec, dict) else None
                if cur and cur.get("latitude") is not None:
                    ts = cur.get("timestamp", 0)
                    if ts >= best_ts:
                        best_ts = ts
                        best_rec = rec
            if best_rec is not None:
                return best_rec

            if len(self.device_locations) >= 1:
                return list(self.device_locations.values())[0]

            return {
                "current": None,
                "history": []
            }


def reverse_geocode_address(lat, lon):
    """Obtém Nome da Rua, Número, Bairro, Cidade, Estado e CEP usando serviço reverso."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'MDM-FRP-Brasil-Manager/2.0 (contato@mdmfrpbrasil.com.br)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            addr = data.get("address", {})
            street = addr.get("road") or addr.get("street") or addr.get("pedestrian") or addr.get("avenue") or addr.get("highway") or "Rua Não Identificada"
            number = addr.get("house_number") or "S/N"
            neighborhood = addr.get("neighbourhood") or addr.get("suburb") or addr.get("city_district") or addr.get("district") or "Bairro Central"
            city = addr.get("city") or addr.get("town") or addr.get("municipality") or "Cidade"
            state = addr.get("state") or addr.get("region") or ""
            state_code = addr.get("ISO3166-2-lvl4", "").split("-")[-1] or state
            cep = addr.get("postcode") or ""

            full = f"{street}, {number} - {neighborhood}, {city} - {state_code}"
            if cep:
                full += f", CEP {cep}"

            return {
                "street": street,
                "number": number,
                "neighborhood": neighborhood,
                "city": city,
                "state": state_code,
                "cep": cep,
                "fullAddress": full
            }
    except Exception as e:
        logger.warning(f"Reverse geocode lookup warning: {e}")
        return {
            "street": "Localização Detectada",
            "number": "S/N",
            "neighborhood": "Setor GPS",
            "city": "Americana",
            "state": "SP",
            "cep": "",
            "fullAddress": f"Lat: {lat:.6f}, Lon: {lon:.6f}"
        }


class BackendHttpHandler(BaseHTTPRequestHandler):
    """Handles HTTP queries from Android BackendSyncManager."""

    def log_message(self, format, *args):
        # Quiet standard HTTP access logs
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/device/state":
            qs = urllib.parse.parse_qs(parsed.query)
            device_id = qs.get("deviceId", ["UNKNOWN"])[0]
            store = BackendStateStore.get_instance()
            state = store.get_device_state(device_id)

            body = json.dumps(state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/device/location":
            qs = urllib.parse.parse_qs(parsed.query)
            device_id = qs.get("deviceId", ["UNKNOWN"])[0]
            store = BackendStateStore.get_instance()
            loc_data = store.get_device_location(device_id)

            body = json.dumps(loc_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/device/complete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                device_id = data.get("deviceId")
                op_id = data.get("operationId")
                store = BackendStateStore.get_instance()
                store.set_device_completed(device_id, op_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                resp = b'{"success":true,"status":"COMPLETED"}'
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        elif parsed.path == "/api/device/location":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                device_id = data.get("deviceId", "UNKNOWN")
                store = BackendStateStore.get_instance()
                store.update_device_location(device_id, data)
                logger.info(f"Location updated for {device_id}: {data.get('latitude')}, {data.get('longitude')}")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                resp = b'{"success":true,"status":"LOCATION_RECORDED"}'
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                logger.error(f"Error recording location: {e}")
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class AdbManager:
    """
    Manages communication with Android devices via embedded ADB,
    hosts the authoritative Backend State Server, and orchestrates official deprovisioning.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.adb_path = self._setup_adb()
        self.apk_path = self._find_resource("MDM_FRP_BRASIL_DEVICE_SERVICE.apk")
        self.default_logo_path = self._find_resource("default_logo.png")
        self.backend_store = BackendStateStore.get_instance()
        self._start_server()
        self._start_backend_http_server()

    def _start_backend_http_server(self):
        try:
            server = HTTPServer(("0.0.0.0", 8088), BackendHttpHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            logger.info("Backend Authority HTTP Server listening on port 8088.")
        except Exception as e:
            logger.warning(f"Could not bind port 8088 (may be already in use): {e}")

    def _get_base_dir(self):
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(__file__))

    def _find_resource(self, filename):
        base = self._get_base_dir()
        candidates = [
            os.path.join(base, "resources", filename),
            os.path.join(base, filename),
            os.path.join(os.path.dirname(base), "dist", filename),
            os.path.join(os.path.dirname(base), "resources", filename),
        ]
        for p in candidates:
            if os.path.exists(p):
                return os.path.abspath(p)
        return ""

    def _setup_adb(self):
        base = self._get_base_dir()
        embedded_adb_dir = os.path.join(base, "resources", "adb")
        if not os.path.exists(embedded_adb_dir):
            embedded_adb_dir = os.path.join(os.path.dirname(base), "adb")

        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        target_adb_dir = os.path.join(local_app_data, "MDM_FRP_BRASIL_DSM", "adb")
        os.makedirs(target_adb_dir, exist_ok=True)

        target_adb_exe = os.path.join(target_adb_dir, "adb.exe")

        files_to_copy = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]
        for f in files_to_copy:
            src = os.path.join(embedded_adb_dir, f)
            dst = os.path.join(target_adb_dir, f)
            if os.path.exists(src):
                try:
                    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                        shutil.copyfile(src, dst)
                except Exception as e:
                    logger.warning(f"Could not update {dst}: {e}")

        if os.path.exists(target_adb_exe):
            return target_adb_exe
        
        direct_exe = os.path.join(embedded_adb_dir, "adb.exe")
        if os.path.exists(direct_exe):
            return direct_exe

        system_adb = shutil.which("adb")
        if system_adb:
            return system_adb

        raise FileNotFoundError("adb.exe não foi encontrado nos recursos internos do aplicativo.")

    def run_cmd(self, args, timeout=15):
        cmd = [self.adb_path] + args
        with self._lock:
            try:
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = subprocess.CREATE_NO_WINDOW

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    creationflags=creationflags
                )
                return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
            except subprocess.TimeoutExpired:
                return -1, "", f"Comando expirou após {timeout}s: {' '.join(cmd)}"
            except Exception as e:
                return -1, "", str(e)

    def _start_server(self):
        try:
            self.run_cmd(["start-server"], timeout=10)
        except Exception as e:
            logger.error(f"Erro ao iniciar servidor ADB: {e}")

    def detectDevices(self):
        code, out, err = self.run_cmd(["devices", "-l"])
        if code != 0:
            return []

        devices = []
        lines = out.splitlines()
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                status = parts[1]

                model = "Desconhecido"
                device = "Desconhecido"

                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1]
                    elif part.startswith("device:"):
                        device = part.split(":", 1)[1]

                devices.append({
                    "serial": serial,
                    "status": status,
                    "model": model,
                    "device": device
                })

        return devices

    def setupReversePort(self, serial=None, port=8088):
        s_args = ["-s", serial] if serial else []
        self.run_cmd(s_args + ["reverse", f"tcp:{port}", f"tcp:{port}"], timeout=5)

    def getDeviceInfo(self, serial=None):
        s_args = ["-s", serial] if serial else []

        code, out, err = self.run_cmd(s_args + ["get-state"])
        if code != 0 or out != "device":
            return {
                "serial": serial or "N/A",
                "status": "unauthorized" if "unauthorized" in err or "unauthorized" in out else "offline",
                "authorized": False,
                "model": "Aguardando autorização",
                "manufacturer": "N/A",
                "android": "N/A",
                "installed": False,
                "package": "br.com.mdmfrpbrasil.deviceservice"
            }

        # Setup ADB reverse for HTTP backend synchronization
        self.setupReversePort(serial, port=8088)

        _, model, _ = self.run_cmd(s_args + ["shell", "getprop", "ro.product.model"])
        _, manufacturer, _ = self.run_cmd(s_args + ["shell", "getprop", "ro.product.manufacturer"])
        _, android_ver, _ = self.run_cmd(s_args + ["shell", "getprop", "ro.build.version.release"])
        _, serial_no, _ = self.run_cmd(s_args + ["shell", "getprop", "ro.serialno"])
        if not serial_no or serial_no == "unknown":
            serial_no = serial or "N/A"

        _, pm_out, _ = self.run_cmd(s_args + ["shell", "pm", "list", "packages", "br.com.mdmfrpbrasil.deviceservice"])
        is_installed = "package:br.com.mdmfrpbrasil.deviceservice" in pm_out

        return {
            "serial": serial_no,
            "status": "device",
            "authorized": True,
            "model": model or "Android Device",
            "manufacturer": manufacturer or "Fabricante",
            "android": android_ver or "N/A",
            "installed": is_installed,
            "package": "br.com.mdmfrpbrasil.deviceservice"
        }

    def isAppInstalled(self, serial=None):
        info = self.getDeviceInfo(serial)
        return info.get("installed", False)

    def installApk(self, apk_path=None, serial=None):
        target_apk = apk_path or self.apk_path
        if not target_apk or not os.path.exists(target_apk):
            return False, f"APK não encontrado: {target_apk}"

        s_args = ["-s", serial] if serial else []

        # Wake screen and turn off verifier flags
        self.run_cmd(s_args + ["shell", "input", "keyevent", "224"], timeout=4)
        self.run_cmd(s_args + ["shell", "settings", "put", "global", "verifier_verify_adb_installs", "0"], timeout=4)
        self.run_cmd(s_args + ["shell", "settings", "put", "global", "package_verifier_enable", "0"], timeout=4)
        self.run_cmd(s_args + ["shell", "pm", "enable", "br.com.mdmfrpbrasil.deviceservice"], timeout=4)

        # 1. Install direct
        code, out, err = self.run_cmd(s_args + ["install", "-r", "-d", "-g", "--bypass-low-target-sdk-block", target_apk], timeout=40)
        output = (out + "\n" + err).strip()
        if code == 0 and "Success" in output:
            self.setupReversePort(serial, port=8088)
            return True, "APK instalado com sucesso!"

        # 2. Standard install
        code, out, err = self.run_cmd(s_args + ["install", "-r", "-d", "-g", target_apk], timeout=40)
        output = (out + "\n" + err).strip()
        if code == 0 and "Success" in output:
            self.setupReversePort(serial, port=8088)
            return True, "APK instalado com sucesso!"

        # 3. Fallback push
        tmp_apk = "/data/local/tmp/service_setup.apk"
        p_code, p_out, p_err = self.run_cmd(s_args + ["push", target_apk, tmp_apk], timeout=20)
        if p_code == 0:
            c_code, c_out, c_err = self.run_cmd(s_args + ["shell", "pm", "install", "-r", "-d", "-g", "--bypass-low-target-sdk-block", tmp_apk], timeout=30)
            self.run_cmd(s_args + ["shell", "rm", "-f", tmp_apk], timeout=4)
            c_output = (c_out + "\n" + c_err).strip()
            if "Success" in c_output:
                self.setupReversePort(serial, port=8088)
                return True, "APK instalado com sucesso!"

        return False, f"Falha na instalação: {output}"

    def startApplication(self, serial=None):
        s_args = ["-s", serial] if serial else []
        cmd = s_args + [
            "shell", "am", "start",
            "-n", "br.com.mdmfrpbrasil.deviceservice/.MainActivity",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER"
        ]
        code, out, err = self.run_cmd(cmd, timeout=15)
        output = (out + "\n" + err).strip()

        if "Error" in output or "Exception" in output:
            return False, f"Erro ao iniciar aplicativo: {output}"
        return True, "Aplicativo iniciado na tela do aparelho."

    def sendConfiguration(self, client, service, val, pix_code, qr_image_path=None, logo_path=None, state="PENDING", serial=None):
        s_args = ["-s", serial] if serial else []

        # Identify device
        info = self.getDeviceInfo(serial)
        device_id = info.get("serial", serial or "UNKNOWN")
        model = info.get("model", "Android Device")

        # 1. Update authoritative backend state to PENDING
        rec = self.backend_store.set_device_pending(device_id, model, client, service, val, pix_code)
        op_id = rec.get("operationId", "OP-2026-OFICIAL")

        # Ensure destination directory exists on device
        app_files_dir = "/sdcard/Android/data/br.com.mdmfrpbrasil.deviceservice/files"
        self.run_cmd(s_args + ["shell", "mkdir", "-p", app_files_dir], timeout=5)

        # 2. Push Logo
        remote_logo = ""
        target_logo = logo_path if (logo_path and os.path.exists(logo_path)) else self.default_logo_path
        if target_logo and os.path.exists(target_logo):
            remote_logo = f"{app_files_dir}/service_logo.png"
            self.run_cmd(s_args + ["push", target_logo, remote_logo], timeout=20)
            self.run_cmd(s_args + ["shell", "chmod", "666", remote_logo])
            self.run_cmd(s_args + ["push", target_logo, "/data/local/tmp/service_logo.png"], timeout=10)

        # 3. Push QR
        remote_qr = ""
        if qr_image_path and os.path.exists(qr_image_path):
            remote_qr = f"{app_files_dir}/service_qr.png"
            self.run_cmd(s_args + ["push", qr_image_path, remote_qr], timeout=20)
            self.run_cmd(s_args + ["shell", "chmod", "666", remote_qr])
            self.run_cmd(s_args + ["push", qr_image_path, "/data/local/tmp/service_qr.png"], timeout=10)

        # Wake up device display, dismiss lockscreen and dismiss keyguard
        self.run_cmd(s_args + ["shell", "input", "keyevent", "224"], timeout=5)
        self.run_cmd(s_args + ["shell", "wm", "dismiss-keyguard"], timeout=5)
        self.run_cmd(s_args + ["shell", "input", "keyevent", "82"], timeout=5)

        # Enable package and MainActivity if previously disabled
        self.run_cmd(s_args + ["shell", "pm", "enable", "br.com.mdmfrpbrasil.deviceservice"], timeout=4)
        self.run_cmd(s_args + ["shell", "pm", "enable", "br.com.mdmfrpbrasil.deviceservice/.MainActivity"], timeout=4)

        safe_client = str(client).replace("'", "").strip()
        safe_service = str(service).replace("'", "").strip()
        safe_val = str(val).replace("'", "").strip()
        safe_pix = str(pix_code).replace("'", "").strip()

        # 4. Broadcast with explicit -p package targeting (required on Android 14)
        bcast_args = [
            "shell", "am", "broadcast",
            "-a", "br.com.mdmfrpbrasil.deviceservice.SET_CONFIG",
            "-p", "br.com.mdmfrpbrasil.deviceservice",
            "--es", "state", "PENDING",
            "--es", "client", f"'{safe_client}'",
            "--es", "service", f"'{safe_service}'",
            "--es", "value", f"'{safe_val}'",
            "--es", "pix", f"'{safe_pix}'",
            "--es", "operation_id", f"'{op_id}'"
        ]
        if remote_logo:
            bcast_args.extend(["--es", "logo_path", f"'{remote_logo}'"])
        if remote_qr:
            bcast_args.extend(["--es", "qr_path", f"'{remote_qr}'"])

        self.run_cmd(s_args + bcast_args, timeout=10)

        # 5. Start Activity with extras
        am_args = [
            "shell", "am", "start",
            "-n", "br.com.mdmfrpbrasil.deviceservice/.MainActivity",
            "--es", "state", "PENDING",
            "--es", "client", f"'{safe_client}'",
            "--es", "service", f"'{safe_service}'",
            "--es", "value", f"'{safe_val}'",
            "--es", "pix", f"'{safe_pix}'",
            "--es", "operation_id", f"'{op_id}'"
        ]
        if remote_logo:
            am_args.extend(["--es", "logo_path", f"'{remote_logo}'"])
        if remote_qr:
            am_args.extend(["--es", "qr_path", f"'{remote_qr}'"])

        code, out, err = self.run_cmd(s_args + am_args, timeout=20)
        self.setupReversePort(serial, port=8088)

        output = (out + "\n" + err).strip()
        if "Error" in output or "Exception" in output:
            return False, f"Erro ao enviar configuração: {output}"

        return True, f"Configuração enviada com sucesso! Estado definido para: PENDING (OP: #{op_id})"

    def sendServicePending(self, serial, client, service, value, pix, logo_path=None, qr_path=None):
        return self.sendConfiguration(
            client=client,
            service=service,
            val=value,
            pix_code=pix,
            qr_image_path=qr_path,
            logo_path=logo_path,
            state="PENDING",
            serial=serial
        )

    def queryDeviceState(self, serial=None):
        st = self.getApplicationStatus(serial)
        return {"state": st.get("status", "PENDING")}

    def getBackendState(self, serial=None):
        info = self.getDeviceInfo(serial)
        dev_id = info.get("serial", serial or "UNKNOWN")
        return self.backend_store.get_device_state(dev_id)

    def set_device_pending(self, serial, client, service, val, pix):
        info = self.getDeviceInfo(serial)
        dev_id = info.get("serial", serial or "UNKNOWN")
        model = info.get("model", "Android Device")
        return self.backend_store.set_device_pending(dev_id, model, client, service, val, pix)

    def authorizeOperation(self, serial=None, authorized_by="ADMIN_EXE"):
        """
        Official Administrative Action: CONFIRMAR OPERAÇÃO
        1. Identifies connected device and validates device ID.
        2. Idempotently sets state in the backend to AUTHORIZED.
        3. Registers date/time, operationId, and authorizedBy.
        4. Transmits authoritative state event to device.
        5. Closes kiosk lock task and navigates to home screen.
        Returns dict with operation details.
        """
        s_args = ["-s", serial] if serial else []
        info = self.getDeviceInfo(serial)
        device_id = info.get("serial", serial or "UNKNOWN")
        model = info.get("model", "Android Device")

        # Authorize in backend store (Idempotent)
        rec = self.backend_store.authorize_device(device_id, model=model, authorized_by=authorized_by)
        op_id = rec.get("operationId")

        # Wake screen
        self.run_cmd(s_args + ["shell", "input", "keyevent", "224"], timeout=4)
        self.run_cmd(s_args + ["shell", "wm", "dismiss-keyguard"], timeout=4)

        # Transmit state to device via broadcast and intent
        self.run_cmd(s_args + [
            "shell", "am", "broadcast",
            "-a", "br.com.mdmfrpbrasil.deviceservice.UNLOCK_DEVICE",
            "-p", "br.com.mdmfrpbrasil.deviceservice",
            "--es", "operation_id", str(op_id),
            "--es", "authorized_by", str(authorized_by)
        ], timeout=8)

        self.run_cmd(s_args + [
            "shell", "am", "broadcast",
            "-a", "br.com.mdmfrpbrasil.deviceservice.RESTORE_STATUS_BAR",
            "-p", "br.com.mdmfrpbrasil.deviceservice"
        ], timeout=8)

        self.run_cmd(s_args + [
            "shell", "am", "broadcast",
            "-a", "br.com.mdmfrpbrasil.deviceservice.BACKEND_STATE_UPDATE",
            "-p", "br.com.mdmfrpbrasil.deviceservice",
            "--es", "state", "AUTHORIZED",
            "--es", "operation_id", str(op_id),
            "--es", "authorized_by", str(authorized_by)
        ], timeout=8)

        # Ensure system dialogs close and user returns to Home screen immediately
        time.sleep(0.5)
        self.run_cmd(s_args + ["shell", "input", "keyevent", "3"], timeout=3) # KEYCODE_HOME

        return rec

    def getApplicationStatus(self, serial=None):
        s_args = ["-s", serial] if serial else []
        code, out, err = self.run_cmd(s_args + ["shell", "cat", "/data/local/tmp/mdm_service_status.json"], timeout=5)

        if code == 0 and out.strip().startswith("{") and out.strip().endswith("}"):
            try:
                return json.loads(out.strip())
            except Exception:
                pass

        # Check backend store
        info = self.getDeviceInfo(serial)
        device_id = info.get("serial", serial or "UNKNOWN")
        backend_st = self.backend_store.get_device_state(device_id)

        code, pid, _ = self.run_cmd(s_args + ["shell", "pidof", "br.com.mdmfrpbrasil.deviceservice"])
        return {
            "status": backend_st.get("status", "EXECUTANDO" if (code == 0 and pid) else "PARADO"),
            "operationId": backend_st.get("operationId", "-"),
            "package": "br.com.mdmfrpbrasil.deviceservice",
            "pid": pid if (code == 0 and pid) else None
        }

    def waitForCompleted(self, serial=None, max_seconds=6.0):
        s_args = ["-s", serial] if serial else []
        start_t = time.time()
        while time.time() - start_t < max_seconds:
            code, out, _ = self.run_cmd(s_args + ["shell", "cat", "/data/local/tmp/mdm_service_status.json"], timeout=3)
            if code == 0 and out:
                if "COMPLETED" in out or "RELEASE_ACK" in out:
                    return True
            time.sleep(0.4)
        return True

    def removeAuthorizedPackage(self, serial=None):
        s_args = ["-s", serial] if serial else []
        pkg = "br.com.mdmfrpbrasil.deviceservice"
        receiver = f"{pkg}/.ServiceConfigReceiver"
        admin = f"{pkg}/.ServiceDeviceAdminReceiver"

        # 1. Acordar tela e remover bloqueio de tela
        self.run_cmd(s_args + ["shell", "input", "keyevent", "82"], timeout=3)
        self.run_cmd(s_args + ["shell", "input", "keyevent", "3"], timeout=3)

        # 2. Enviar broadcasts explícitos de destravamento e autodestruição para o receiver em primeiro plano
        self.run_cmd(s_args + ["shell", "am", "broadcast", "-a", f"{pkg}.UNLOCK_DEVICE", "-n", receiver, "--receiver-foreground"], timeout=5)
        self.run_cmd(s_args + ["shell", "am", "broadcast", "-a", f"{pkg}.DESTROY_APK", "-n", receiver, "--receiver-foreground"], timeout=5)

        # 3. Disparar MainActivity com comando explícito de autodestruição interna (invoca dpm.clearDeviceOwnerApp)
        self.run_cmd(s_args + ["shell", "am", "start", "-n", f"{pkg}/.MainActivity", "--es", "action", "DESTROY_APK", "--ez", "destroy", "true"], timeout=5)
        time.sleep(1.0)

        # 4. Remover administrador de dispositivo (DPM) para permitir desinstalação
        self.run_cmd(s_args + ["shell", "dpm", "remove-active-admin", admin], timeout=8)
        self.run_cmd(s_args + ["shell", "dpm", "remove-active-admin", f"{pkg}/.DeviceAdminReceiver"], timeout=5)

        # 5. Forçar parada e limpar dados
        self.run_cmd(s_args + ["shell", "am", "force-stop", pkg], timeout=8)
        self.run_cmd(s_args + ["shell", "pm", "clear", pkg], timeout=8)

        # 6. Desinstalar pacote em múltiplos níveis (usuário 0 e global)
        self.run_cmd(s_args + ["shell", "pm", "uninstall", "--user", "0", pkg], timeout=15)
        code, out, err = self.run_cmd(s_args + ["uninstall", pkg], timeout=25)
        combined = (out + "\n" + err).strip()

        # 7. Desativar pacote caso ainda persista
        self.run_cmd(s_args + ["shell", "pm", "disable-user", "--user", "0", pkg], timeout=8)

        # Limpar arquivos residuais na pasta temporária
        self.run_cmd(s_args + [
            "shell", "rm", "-f",
            "/data/local/tmp/service_logo.png",
            "/data/local/tmp/service_qr.png",
            "/data/local/tmp/mdm_service_status.json"
        ], timeout=4)

        if self.verifyPackageRemoved(serial) or "Success" in combined:
            return True, "APK destruído e desinstalado com sucesso do smartphone."

        return False, combined if combined else "Falha ao desinstalar pacote do sistema."

    def uninstall_device_apk(self, serial=None):
        return self.removeAuthorizedPackage(serial)


    def verifyPackageRemoved(self, serial=None):
        s_args = ["-s", serial] if serial else []
        code, out, _ = self.run_cmd(s_args + ["shell", "pm", "list", "packages", "br.com.mdmfrpbrasil.deviceservice"], timeout=8)
        if "package:br.com.mdmfrpbrasil.deviceservice" in out:
            return False
        return True

    def fetch_ip_location(self, device_id="UNKNOWN"):
        """Busca localização via IP Geolocation quando o celular estiver sem GPS/Internet."""
        try:
            url = "http://ip-api.com/json/?fields=status,country,regionName,city,zip,lat,lon,isp,query"
            req = urllib.request.Request(url, headers={'User-Agent': 'MDM-FRP-Brasil-Manager/2.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("status") == "success":
                    lat = float(data.get("lat"))
                    lon = float(data.get("lon"))
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    cep = data.get("zip", "")
                    isp = data.get("isp", "")

                    geo = reverse_geocode_address(lat, lon)
                    payload = {
                        "deviceId": device_id,
                        "latitude": lat,
                        "longitude": lon,
                        "accuracy": 15.0,
                        "timestamp": int(time.time() * 1000),
                        "provider": "IP / Redes Móveis",
                        "batteryLevel": 100,
                        "networkStatus": "online (IP)",
                        "street": geo.get("street") or f"Área Central ({city})",
                        "number": geo.get("number") or "S/N",
                        "neighborhood": geo.get("neighborhood") or "Região Metropolitana",
                        "city": city or geo.get("city") or "Americana",
                        "state": region or geo.get("state") or "SP",
                        "cep": cep or geo.get("cep") or "",
                        "fullAddress": geo.get("fullAddress") or f"{city} - {region}, Brasil (IP: {data.get('query')})",
                        "status": "LOCATION_ACQUIRED_IP",
                        "type": "IP_GEOLOCATION"
                    }
                    self.backend_store.update_device_location(device_id, payload)
                    return payload
        except Exception as e:
            logger.warning(f"IP Geolocation error: {e}")
        return None

    def request_device_location(self, serial=None):
        """Envia broadcast explícito para o aparelho coletar coordenadas imediatamente."""
        s_args = ["-s", serial] if serial else []
        # Ativa o modo de alta precisão do GPS via ADB
        self.run_cmd(s_args + ["shell", "settings", "put", "secure", "location_mode", "3"], timeout=3)
        self.run_cmd(s_args + ["shell", "cmd", "location", "set-location-enabled", "true"], timeout=3)

        # Assegura encaminhamento de porta 8088
        self.run_cmd(s_args + ["reverse", "tcp:8088", "tcp:8088"], timeout=5)
        # Concede permissões caso necessário
        self.run_cmd(s_args + ["shell", "pm", "grant", "br.com.mdmfrpbrasil.deviceservice", "android.permission.ACCESS_FINE_LOCATION"], timeout=5)
        self.run_cmd(s_args + ["shell", "pm", "grant", "br.com.mdmfrpbrasil.deviceservice", "android.permission.ACCESS_COARSE_LOCATION"], timeout=5)
        self.run_cmd(s_args + ["shell", "pm", "grant", "br.com.mdmfrpbrasil.deviceservice", "android.permission.ACCESS_BACKGROUND_LOCATION"], timeout=5)
        # Dispara comando de localização sob demanda com -p explícito para entrega em segundo plano
        code, out, err = self.run_cmd(s_args + ["shell", "am", "broadcast", "-a", "br.com.mdmfrpbrasil.deviceservice.REQUEST_LOCATION", "-p", "br.com.mdmfrpbrasil.deviceservice"], timeout=8)

        # Assegura que sempre haverá localização válida (via IP fallback se o GPS do celular estiver offline)
        loc = self.get_device_location(serial)
        if not loc or not loc.get("current") or loc["current"].get("latitude") is None:
            self.fetch_ip_location(serial or "UNKNOWN")

        return code == 0, out

    def get_device_location(self, device_id):
        loc = self.backend_store.get_device_location(device_id)
        if not loc or not loc.get("current") or loc["current"].get("latitude") is None:
            # Fallback automático sob demanda
            self.fetch_ip_location(device_id)
            loc = self.backend_store.get_device_location(device_id)
        return loc
