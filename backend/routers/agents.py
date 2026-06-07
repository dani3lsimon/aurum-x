# backend/routers/agents.py
from fastapi import APIRouter
from services.supabase_service import get_latest_agent_scores, get_supabase
from collectors.positioning_collector import PositioningCollector

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/scores")
async def get_agent_scores():
    return await get_latest_agent_scores()


@router.get("/cot")
async def get_cot_data():
    """Real CFTC public-API gold positioning (managed money primary signal). No key required."""
    collector = PositioningCollector()
    return await collector.get_latest()


@router.get("/cot/refresh")
async def refresh_cot_data():
    """Force-refresh CFTC data, bypassing the 6h cache."""
    collector = PositioningCollector()
    return await collector.update_from_cftc()


@router.get("/history/{agent_name}")
async def get_agent_history(agent_name: str, limit: int = 50):
    sb = get_supabase()
    result = (
        sb.table("agent_scores")
        .select("*")
        .eq("agent_name", agent_name)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
