# backend/routers/agents.py
from fastapi import APIRouter
from services.supabase_service import get_latest_agent_scores, get_supabase

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/scores")
async def get_agent_scores():
    return await get_latest_agent_scores()


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
