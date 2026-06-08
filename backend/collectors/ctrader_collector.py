# backend/collectors/ctrader_collector.py
"""
cTrader Tick Bridge collector.

Connects to the AURUM-X cTrader VPS tick bridge (70.156.8.139), which holds a
live cTrader Open API session and re-broadcasts XAUUSD ticks over a local
WebSocket/REST relay — giving the dashboard a direct broker feed with no
OAuth/token exposure in the browser. Falls back to OANDA's v20 REST API
(the previous primary source) if the bridge is unreachable or not yet warmed up.
"""
import httpx
from config import get_settings
from services.redis_service import cache_get, cache_set
import logging
from datetime import datetime, timezone

logger   = logging.getLogger(__name__)
settings = get_settings()


class CTraderCollector:

    def __init__(self):
        self.bridge_url   = getattr(settings, 'ctrader_bridge_url', 'http://70.156.8.139:8081')
        self.bridge_token = getattr(settings, 'ctrader_bridge_token', '')
        self.headers      = {'Authorization': f'Bearer {self.bridge_token}'}

    async def get_gold_price(self) -> dict:
        cache_key = "ctrader_xauusd_price"
        cached    = await cache_get(cache_key)
        if cached:
            return cached

        try:
            async with httpx.AsyncClient(timeout=5, headers=self.headers) as client:
                resp = await client.get(f"{self.bridge_url}/price")
                resp.raise_for_status()
                data = resp.json()

            if not data.get("mid") and not data.get("bid"):
                raise ValueError("bridge returned no price yet")

            result = {
                "symbol":    "XAUUSD",
                "price":     data.get("mid") or data.get("bid"),
                "bid":       data.get("bid"),
                "ask":       data.get("ask"),
                "spread":    data.get("spread"),
                "timestamp": data.get("timestamp"),
                "source":    "ctrader_live",
            }
            await cache_set(cache_key, result, ttl_seconds=5)
            logger.debug(f"cTrader bridge price: {result['price']}")
            return result

        except Exception as e:
            logger.warning(f"cTrader bridge unavailable ({e}), falling back to OANDA")
            from collectors.oanda_collector import OandaCollector
            return await OandaCollector().get_gold_price()

    async def get_bridge_health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5, headers=self.headers) as client:
                resp = await client.get(f"{self.bridge_url}/health")
                return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    async def get_ohlcv(self, timeframe: str = "1h", bars: int = 24) -> list:
        """
        OHLCV bars for XAUUSD. Cached 5 minutes.
        The tick bridge only streams live spot ticks (no historical bar
        aggregation yet) — honest no-data: returns [] rather than synthesizing
        candles. OHLCV continues to be served by the OANDA collector elsewhere
        in the pipeline.
        """
        cache_key = f"ctrader_xauusd_ohlcv_{timeframe}_{bars}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        result: list = []
        await cache_set(cache_key, result, ttl_seconds=300)
        return result
