# backend/services/supabase_service.py
from supabase import create_client, Client
from config import get_settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
settings = get_settings()
_supabase: Client = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
    return _supabase


# ── Forecasts ──────────────────────────────────────────────────────────────

async def insert_forecast(forecast_data: dict) -> dict:
    sb = get_supabase()
    result = sb.table("forecasts").insert(forecast_data).execute()
    return result.data[0] if result.data else None


async def get_latest_forecast() -> dict:
    sb = get_supabase()
    result = (
        sb.table("forecasts")
        .select("*")
        .order("timestamp", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_forecast_history(hours: int = 48) -> list:
    sb = get_supabase()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    result = (
        sb.table("forecasts")
        .select("*")
        .gte("timestamp", cutoff)
        .order("timestamp", desc=True)
        .execute()
    )
    return result.data


# ── Agent Scores ───────────────────────────────────────────────────────────

async def insert_agent_score(score_data: dict) -> dict:
    sb  = get_supabase()
    raw = score_data.get("raw_data", {}) or {}
    record = {
        "agent_name":       score_data.get("agent_name"),
        "score":            score_data.get("score"),
        "confidence":       score_data.get("confidence"),
        "rationale":        score_data.get("rationale"),
        "raw_data":         raw,
        "regime":           score_data.get("regime") or raw.get("regime"),
        "timestamp":        score_data.get("timestamp"),
        "signal_strength":  raw.get("signal_strength"),
        "directional_bias": raw.get("directional_bias"),
        "data_quality":     raw.get("data_quality", "medium"),
        "notable_risk":     raw.get("notable_risk"),
        "key_factors":      raw.get("key_factors", []),
        "data_source":      score_data.get("data_source"),
    }
    result = sb.table("agent_scores").insert(record).execute()

    history_record = {
        "agent_name":       record["agent_name"],
        "score":            record["score"],
        "confidence":       record["confidence"],
        "directional_bias": record["directional_bias"],
        "timestamp":        record["timestamp"],
    }
    sb.table("agent_score_history").insert(history_record).execute()

    return result.data[0] if result.data else None


async def get_latest_agent_scores() -> list:
    """Latest score per unique agent — NOT the last N rows overall.
    Agents run on different cadences (30min/2hr/6hr/daily), so a flat
    timestamp-DESC limit silently drops whichever agents ran earliest
    in a batch once enough other agents insert after them."""
    sb = get_supabase()
    result = (
        sb.table("agent_scores")
        .select("*")
        .order("timestamp", desc=True)
        .limit(50)
        .execute()
    )
    latest_by_agent = {}
    for row in result.data:
        name = row.get("agent_name")
        if name not in latest_by_agent:
            latest_by_agent[name] = row
    return list(latest_by_agent.values())


# ── Regime ─────────────────────────────────────────────────────────────────

async def insert_regime(regime_data: dict) -> dict:
    sb = get_supabase()
    result = sb.table("regime_history").insert(regime_data).execute()
    return result.data[0] if result.data else None


# ── Alerts ─────────────────────────────────────────────────────────────────

async def insert_alert(alert_data: dict) -> dict:
    sb = get_supabase()
    result = sb.table("alerts").insert(alert_data).execute()
    return result.data[0] if result.data else None


# ── News ───────────────────────────────────────────────────────────────────

async def get_recent_news(limit: int = 20) -> list:
    sb = get_supabase()
    result = (
        sb.table("news_articles")
        .select("*")
        .order("published_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


async def insert_news_articles(articles: list) -> int:
    if not articles:
        return 0
    sb = get_supabase()
    result = sb.table("news_articles").upsert(articles, on_conflict="url").execute()
    return len(result.data) if result.data else 0


# ── Economic Releases ──────────────────────────────────────────────────────

async def insert_economic_releases(releases: list) -> int:
    if not releases:
        return 0
    sb = get_supabase()
    result = (
        sb.table("economic_releases")
        .upsert(releases, on_conflict="event,release_date")
        .execute()
    )
    return len(result.data) if result.data else 0


async def get_upcoming_releases(days: int = 7) -> list:
    sb = get_supabase()
    now = datetime.utcnow().isoformat()
    future = (datetime.utcnow() + timedelta(days=days)).isoformat()
    result = (
        sb.table("economic_releases")
        .select("*")
        .gte("release_date", now)
        .lte("release_date", future)
        .order("release_date")
        .execute()
    )
    return result.data


async def get_todays_releases() -> list:
    sb = get_supabase()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59).isoformat()
    result = (
        sb.table("economic_releases")
        .select("*")
        .gte("release_date", today_start)
        .lte("release_date", today_end)
        .order("release_date")
        .execute()
    )
    return result.data


# ── Positioning ────────────────────────────────────────────────────────────

async def get_latest_positioning() -> dict:
    sb = get_supabase()
    result = (
        sb.table("cftc_positioning")
        .select("*")
        .order("report_date", desc=True)
        .limit(5)
        .execute()
    )
    return result.data


# ── Scenarios ──────────────────────────────────────────────────────────────

async def get_latest_scenarios() -> list:
    sb = get_supabase()
    result = (
        sb.table("scenarios")
        .select("*")
        .order("created_at", desc=True)
        .limit(4)
        .execute()
    )
    return result.data
