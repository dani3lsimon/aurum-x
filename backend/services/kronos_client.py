# backend/services/kronos_client.py
"""
Thin HTTP client for the Kronos microservice.
No torch dependency — all inference happens on the Kronos host.
Returns {'available': False} gracefully on any failure.
"""
import httpx
import asyncio
import logging
from config import get_settings
from services.redis_service import cache_get, cache_set

logger   = logging.getLogger(__name__)
settings = get_settings()

CACHE_TTL = 300   # 5 minutes


async def get_kronos_forecast(candles: list, freq: str, pred_len: int = 12) -> dict:
    """
    Posts candles to Kronos service, returns forecast dict.
    Caches per-timeframe. Returns {'available': False} on any error.
    """
    cache_key = f'kronos_{freq}'
    cached    = await cache_get(cache_key)
    if cached:
        return cached

    url   = getattr(settings, 'kronos_service_url', '')
    token = getattr(settings, 'kronos_auth_token', '')

    if not url:
        return {'available': False, 'reason': 'KRONOS_SERVICE_URL not set'}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f'{url}/forecast',
                json={'candles': candles, 'freq': freq, 'pred_len': pred_len},
                headers={'Authorization': f'Bearer {token}'},
            )
            resp.raise_for_status()
            result = resp.json()
            result['available'] = True
            await cache_set(cache_key, result, ttl_seconds=CACHE_TTL)
            return result

    except Exception as e:
        logger.warning(f'Kronos service unavailable ({freq}): {e}')
        return {'available': False, 'reason': str(e)}


async def get_kronos_all_timeframes(oanda_candles_by_tf: dict) -> dict:
    """Fetch Kronos forecast for all 3 timeframes in parallel."""
    tasks = {
        tf: get_kronos_forecast(candles, tf)
        for tf, candles in oanda_candles_by_tf.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {
        tf: r if not isinstance(r, Exception) else {'available': False}
        for tf, r in zip(tasks.keys(), results)
    }
