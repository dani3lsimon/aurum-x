# backend/services/redis_service.py
# Redis replaced with Supabase cache table — same interface, no Redis dependency.
# Uses a `cache` table with key / value (JSONB) / expires_at columns.
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_supabase_client = None


def _get_sb():
    global _supabase_client
    if _supabase_client is None:
        from services.supabase_service import get_supabase
        _supabase_client = get_supabase()
    return _supabase_client


async def cache_set(key: str, value, ttl_seconds: int = 300):
    """Write a value to the Supabase cache table with a TTL."""
    try:
        sb = _get_sb()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        # Ensure value is JSON-serialisable
        if not isinstance(value, (dict, list)):
            value = {"_v": value}
        sb.table("cache").upsert(
            {"key": key, "value": value, "expires_at": expires_at},
            on_conflict="key"
        ).execute()
    except Exception as e:
        logger.warning(f"cache_set [{key}] failed: {e}")


async def cache_get(key: str):
    """Read a value from the Supabase cache table. Returns None if missing or expired."""
    try:
        sb = _get_sb()
        now = datetime.now(timezone.utc).isoformat()
        result = (
            sb.table("cache")
            .select("value, expires_at")
            .eq("key", key)
            .gt("expires_at", now)
            .limit(1)
            .execute()
        )
        if result.data:
            v = result.data[0]["value"]
            # Unwrap scalar values stored as {"_v": x}
            if isinstance(v, dict) and list(v.keys()) == ["_v"]:
                return v["_v"]
            return v
        return None
    except Exception as e:
        logger.warning(f"cache_get [{key}] failed: {e}")
        return None


async def cache_delete(key: str):
    try:
        sb = _get_sb()
        sb.table("cache").delete().eq("key", key).execute()
    except Exception as e:
        logger.warning(f"cache_delete [{key}] failed: {e}")


async def publish_event(channel: str, message: dict):
    """No-op — pub/sub handled via Supabase Realtime directly."""
    pass


async def cleanup_expired():
    """Delete expired cache rows — call periodically from scheduler."""
    try:
        sb = _get_sb()
        now = datetime.now(timezone.utc).isoformat()
        sb.table("cache").delete().lt("expires_at", now).execute()
        logger.debug("Cache cleanup: expired rows deleted")
    except Exception as e:
        logger.warning(f"Cache cleanup failed: {e}")
