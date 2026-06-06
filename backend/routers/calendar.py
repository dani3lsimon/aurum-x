# backend/routers/calendar.py
from fastapi import APIRouter
from services.supabase_service import (
    get_upcoming_releases,
    get_todays_releases,
    get_supabase,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/upcoming")
async def get_upcoming(days: int = 7):
    """Economic releases for the next N days."""
    return await get_upcoming_releases(days=days)


@router.get("/today")
async def get_today():
    """All economic releases scheduled for today."""
    return await get_todays_releases()


@router.get("/recent")
async def get_recent_releases(limit: int = 20):
    """Most recently detected actual releases."""
    sb = get_supabase()
    result = (
        sb.table("economic_releases")
        .select("*")
        .not_.is_("actual", "null")
        .order("release_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


@router.get("/high-impact")
async def get_high_impact(days: int = 7):
    """Only high-impact and critical-gold-sensitivity events."""
    from datetime import datetime, timedelta
    sb = get_supabase()
    now = datetime.utcnow().isoformat()
    future = (datetime.utcnow() + timedelta(days=days)).isoformat()
    result = (
        sb.table("economic_releases")
        .select("*")
        .gte("release_date", now)
        .lte("release_date", future)
        .in_("gold_sensitivity", ["high", "critical"])
        .order("release_date")
        .execute()
    )
    return result.data
