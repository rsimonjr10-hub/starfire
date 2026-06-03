"""
Admin router — service health, bridge status, manual report triggers.
Protected by the inter-service secret header.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from app.config import settings
from app.integrations.lumiscapital_bridge import lumiscapital_bridge
from app.integrations.osiris_bridge import osiris_bridge

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_secret(x_service_secret: Optional[str] = Header(None)):
    if x_service_secret != settings.inter_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return x_service_secret


@router.get("/status")
async def system_status(_: str = Depends(verify_secret)):
    """Full status of STARFIRE and connected services."""
    lumis_ok = await lumiscapital_bridge.ping() if lumiscapital_bridge.is_available() else None
    osiris_ok = await osiris_bridge.ping() if osiris_bridge.is_available() else None

    return {
        "starfire": "online",
        "services": {
            "lumisnovacapital": {
                "configured": lumiscapital_bridge.is_available(),
                "url": settings.lumiscapital_service_url or "not set",
                "reachable": lumis_ok,
            },
            "osiris": {
                "configured": osiris_bridge.is_available(),
                "url": settings.osiris_service_url or "not set",
                "reachable": osiris_ok,
            },
        },
        "direct_fmp": bool(settings.fmp_api_key),
    }


@router.post("/report/trigger")
async def trigger_report(
    report_type: str = "daily",
    telegram_id: Optional[int] = None,
    _: str = Depends(verify_secret),
):
    """Manually trigger a report send from Lumisnovacapital to a user."""
    if not lumiscapital_bridge.is_available():
        raise HTTPException(status_code=503, detail="Lumisnovacapital service not configured")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id required")

    sent = await lumiscapital_bridge.request_report(report_type, telegram_id)
    return {"sent": sent, "report_type": report_type, "telegram_id": telegram_id}


@router.get("/osiris/status")
async def osiris_status(_: str = Depends(verify_secret)):
    """Get current OSIRIS execution status."""
    if not osiris_bridge.is_available():
        return {"configured": False, "message": "OSIRIS running as local executor"}
    status = await osiris_bridge.get_status()
    return {"configured": True, "status": status}
