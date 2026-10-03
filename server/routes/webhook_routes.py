import os
import json
import uuid
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from server.pix import process_pix_webhook
from server.models import PixWebhookSimulationRequest
from server.auth import get_current_admin
from server.database import get_db_connection

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

@router.post("/pix")
async def receive_pix_webhook(request: Request, x_idempotency_key: str = Header(None), x_webhook_secret: str = Header(None)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    secret = os.getenv("WEBHOOK_SECRET")
    auth_header = request.headers.get("authorization", "")

    is_authorized = False
    if secret and x_webhook_secret == secret:
        is_authorized = True
    elif auth_header.startswith("Bearer "):
        from server.auth import decode_token
        try:
            payload = decode_token(auth_header.split(" ")[1])
            if payload.get("role") in ("superadmin", "support") or payload.get("admin_id"):
                is_authorized = True
        except Exception:
            pass

    if not is_authorized:
        from server.auth import log_audit_event
        log_audit_event(
            "SECURITY_INTRUSION_ATTEMPT",
            details={
                "attack_type": "UNAUTHORIZED_WEBHOOK_CALL",
                "target_path": "/api/v1/webhooks/pix",
                "detail": "Tentativa não autorizada de disparar webhook de pagamento PIX sem segredo ou token administrativo.",
                "user_agent": request.headers.get("user-agent", "Unknown")
            },
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado: Esta rota exige autenticação criptográfica ou token administrativo."
        )

    raw_body = await request.body()
    payload_str = raw_body.decode("utf-8")

    try:
        data = json.loads(payload_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo da requisição não é um JSON válido.")

    txid = data.get("txid") or data.get("pix", [{}])[0].get("txid")
    if not txid:
        raise HTTPException(status_code=400, detail="Campo 'txid' ausente no payload do webhook.")

    idempotency_key = x_idempotency_key or data.get("idempotency_key") or data.get("endToEndId") or f"WH-{txid}-{data.get('horario', str(uuid.uuid4()))}"

    result = process_pix_webhook(
        txid=txid,
        idempotency_key=idempotency_key,
        raw_payload=payload_str,
        event_status="PAID"
    )

    return result

@router.post("/pix/simulate")
def simulate_pix_webhook(req: PixWebhookSimulationRequest, request: Request, x_webhook_secret: str = Header(None)):
    """
    Endpoint para testes ou aprovação manual de cobrança PIX.
    Protegido: Requer token de administrador ou X-Webhook-Secret válido.
    """
    secret = os.getenv("WEBHOOK_SECRET")
    auth_header = request.headers.get("authorization", "")
    
    is_authorized = False
    if secret and x_webhook_secret == secret:
        is_authorized = True
    elif auth_header.startswith("Bearer "):
        # Check if caller has valid admin bearer token
        from server.auth import decode_token
        try:
            payload = decode_token(auth_header.split(" ")[1])
            if payload.get("role") in ("superadmin", "support") or payload.get("admin_id"):
                is_authorized = True
        except Exception:
            pass

    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado: Esta ação de simulação/aprovação exige autenticação administrativa."
        )

    idem_key = req.idempotency_key or f"SIM-{req.txid}-{uuid.uuid4().hex[:6]}"
    raw_payload = json.dumps({"simulated": True, "txid": req.txid, "status": req.status})

    result = process_pix_webhook(
        txid=req.txid,
        idempotency_key=idem_key,
        raw_payload=raw_payload,
        event_status=req.status
    )
    return result
