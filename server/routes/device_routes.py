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
            cursor.execute(
                "UPDATE devices SET last_seen = CURRENT_TIMESTAMP, last_sync = CURRENT_TIMESTAMP WHERE serial = ?",
                (dev_id,)
            )
        else:
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

    return {"success": True, "status": "LOCATION_RECORDED", "deviceId": dev_id}
