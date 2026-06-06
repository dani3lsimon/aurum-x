# backend/routers/alerts.py
from fastapi import APIRouter
from services.supabase_service import get_supabase

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/recent")
async def get_recent_alerts(limit: int = 20):
    sb = get_supabase()
    result = (
        sb.table("alerts")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


@router.patch("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    sb = get_supabase()
    result = (
        sb.table("alerts")
        .update({"acknowledged": True})
        .eq("id", alert_id)
        .execute()
    )
    return result.data[0] if result.data else {"error": "not found"}
