# backend/routers/scenarios.py
from fastapi import APIRouter
from services.supabase_service import get_supabase, get_latest_scenarios

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("/latest")
async def get_latest_scenarios_endpoint():
    return await get_latest_scenarios()


@router.get("/history")
async def get_scenario_history(limit: int = 20):
    sb = get_supabase()
    result = (
        sb.table("scenarios")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
