import json
import uuid
from fastapi import APIRouter, Request, HTTPException, Header
from server.pix import process_pix_webhook
from server.models import PixWebhookSimulationRequest

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

@router.post("/pix")
async def receive_pix_webhook(request: Request, x_idempotency_key: str = Header(None)):
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
def simulate_pix_webhook(req: PixWebhookSimulationRequest):
    """
    Endpoint para testes locais ou aprovação manual de cobrança PIX.
    Processa de forma estritamente idempotente.
    """
    idem_key = req.idempotency_key or f"SIM-{req.txid}-{uuid.uuid4().hex[:6]}"
    raw_payload = json.dumps({"simulated": True, "txid": req.txid, "status": req.status})

    result = process_pix_webhook(
        txid=req.txid,
        idempotency_key=idem_key,
        raw_payload=raw_payload,
        event_status=req.status
    )
    return result
