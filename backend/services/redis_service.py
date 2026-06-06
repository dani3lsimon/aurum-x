# backend/services/redis_service.py
import redis.asyncio as redis
import json
import logging
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = await redis.from_url(
                settings.redis_url, decode_responses=True
            )
            await _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}. Running without cache.")
            _redis_client = None
    return _redis_client


async def cache_set(key: str, value: dict, ttl_seconds: int = 300):
    try:
        r = await get_redis()
        if r:
            await r.setex(key, ttl_seconds, json.dumps(value))
    except Exception as e:
        logger.warning(f"cache_set failed for {key}: {e}")


async def cache_get(key: str) -> dict | None:
    try:
        r = await get_redis()
        if r:
            data = await r.get(key)
            return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"cache_get failed for {key}: {e}")
    return None


async def cache_delete(key: str):
    try:
        r = await get_redis()
        if r:
            await r.delete(key)
    except Exception as e:
        logger.warning(f"cache_delete failed for {key}: {e}")


async def publish_event(channel: str, message: dict):
    try:
        r = await get_redis()
        if r:
            await r.publish(channel, json.dumps(message))
    except Exception as e:
        logger.warning(f"publish_event failed on {channel}: {e}")
