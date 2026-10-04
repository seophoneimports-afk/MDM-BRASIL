import time
from fastapi import APIRouter, Request, Query
from server.database import get_db_connection, db_transaction
from server.auth import log_audit_event

router = APIRouter(tags=["APK Device Online Sync"])

@router.get("/api/device/state")
@router.get("/api/v1/device/state")
def get_device_state(
    deviceId: str = Query(None),
    serial: str = Query(None)
):
    dev_id = deviceId or serial or "UNKNOWN_DEVICE"
    dev_id = dev_id.strip()

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE serial = ?", (dev_id,))
        row = cursor.fetchone()

        if row:
            lock_status = (row["lock_status"] or "LOCKED").upper()
            op_id = row["operation_id"] or f"OP-ONLINE-{row['id']}"
            cmd = row["pending_command"] if "pending_command" in row.keys() else None
            msg = row["pending_message"] if "pending_message" in row.keys() else None
            if cmd:
                cursor.execute(
                    "UPDATE devices SET pending_command = NULL, last_seen = CURRENT_TIMESTAMP, last_sync = CURRENT_TIMESTAMP WHERE serial = ?",
                    (dev_id,)
                )
            else:
                cursor.execute(
                    "UPDATE devices SET last_seen = CURRENT_TIMESTAMP, last_sync = CURRENT_TIMESTAMP WHERE serial = ?",
                    (dev_id,)
                )
        else:
            cmd = None
            msg = None
            # Register newly discovered device in default locked state
            cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            u = cursor.fetchone()
            owner_id = u["id"] if u else 1
            op_id = f"OP-INIT-{int(time.time())}"
            cursor.execute(
                """
                INSERT INTO devices (user_id, serial, model, lock_status, operation_id, first_seen, last_seen, last_sync)
                VALUES (?, ?, 'Android Managed Device', 'LOCKED', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (owner_id, dev_id, op_id)
            )
            lock_status = "LOCKED"

    # Normalize response for APK BackendSyncManager
    if lock_status in ("UNLOCKED", "PAID", "RELEASED", "ACTIVE", "COMPLETED"):
        normalized_status = "PAID"
    else:
        normalized_status = "PENDING"

    return {
        "status": normalized_status,
        "state": normalized_status,
        "operationId": op_id,
        "authorizedBy": "MDM_CLOUD_AUTHORITY",
        "deviceId": dev_id,
        "lock_status": lock_status,
        "command": cmd,
        "message": msg,
        "timestamp": int(time.time() * 1000)
    }

@router.post("/api/device/complete")
@router.post("/api/v1/device/complete")
async def report_device_complete(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    dev_id = data.get("deviceId", "UNKNOWN")
    op_id = data.get("operationId", "")
    status = data.get("status", "COMPLETED")

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE devices 
            SET lock_status = 'UNLOCKED',
                last_seen = CURRENT_TIMESTAMP,
                last_sync = CURRENT_TIMESTAMP
            WHERE serial = ?
            """,
            (dev_id,)
        )

    log_audit_event("DEVICE_ONLINE_ACK_COMPLETED", details={"deviceId": dev_id, "operationId": op_id, "status": status})
    return {"success": True, "status": "COMPLETED", "deviceId": dev_id}

@router.post("/api/device/location")
@router.post("/api/v1/device/location")
async def report_device_location(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    dev_id = data.get("deviceId", "UNKNOWN")
    lat = data.get("latitude")
    lon = data.get("longitude")
    acc = data.get("accuracy")
    bat = data.get("batteryLevel")
    net = data.get("networkStatus")
    street = data.get("street")
    neighborhood = data.get("neighborhood")
    city = data.get("city")
    state = data.get("state")

    # If coordinates are missing (e.g. device indoors or status LOCATION_UNAVAILABLE), attempt IP-based geolocation fallback
    if lat is None or lon is None:
        client_ip = request.headers.get("x-forwarded-for")
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host

        if client_ip and not client_ip.startswith(("127.", "10.", "192.168.", "172.")):
            try:
                import urllib.request
                import json
                req = urllib.request.Request(f"https://ipwho.is/{client_ip}", headers={'User-Agent': 'MDM-Brasil/2.0'})
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    geo = json.loads(resp.read().decode('utf-8'))
                    if geo.get("success"):
                        lat = geo.get("latitude")
                        lon = geo.get("longitude")
                        if not city: city = geo.get("city")
                        if not state: state = geo.get("region_code")
                        if not acc: acc = 250.0
            except Exception:
                pass

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE devices 
            SET latitude = COALESCE(?, latitude),
                longitude = COALESCE(?, longitude),
                accuracy = COALESCE(?, accuracy),
                battery_level = COALESCE(?, battery_level),
                network_status = COALESCE(?, network_status),
                street = COALESCE(?, street),
                neighborhood = COALESCE(?, neighborhood),
                city = COALESCE(?, city),
                state = COALESCE(?, state),
                last_seen = CURRENT_TIMESTAMP,
                last_sync = CURRENT_TIMESTAMP
            WHERE serial = ?
            """,
            (lat, lon, acc, bat, net, street, neighborhood, city, state, dev_id)
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            u = cursor.fetchone()
            owner_id = u["id"] if u else 1
            cursor.execute(
                """
                INSERT INTO devices (
                    user_id, serial, model, lock_status, operation_id,
                    latitude, longitude, accuracy, battery_level, network_status,
                    street, neighborhood, city, state, first_seen, last_seen, last_sync
                )
                VALUES (?, ?, 'Android Managed Device', 'LOCKED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (owner_id, dev_id, f"OP-LOC-{int(time.time())}", lat, lon, acc, bat, net, street, neighborhood, city, state)
            )

    return {
        "success": True,
        "status": "LOCATION_RECORDED",
        "deviceId": dev_id,
        "latitude": lat,
        "longitude": lon,
        "city": city,
        "state": state
    }

@router.post("/api/v1/client/devices/{serial}/request-location")
def trigger_device_location_request(serial: str):
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE serial = ?", (serial,))
    log_audit_event("DEVICE_LOCATION_REQUEST_TRIGGERED", details={"serial": serial})
    return {"success": True, "message": f"Sinal de rastreamento enviado para {serial}. O APK atualizará o GPS na nuvem."}
