# backend/collectors/ctrader_collector.py
"""
Live XAUUSD price collector.

NOTE on cTrader: a real, active cTrader Open API application ("ChartVisionAI",
client ID/secret/account ID already in CTRADER_* env vars on Railway) exists,
but the OAuth2 + official Python OpenAPI client integration that would let this
*deployed backend process* talk to cTrader directly has not been built yet
(tracked separately as the broker-integration task). The "cTrader MCP connector"
referenced in the v3 plan is a tool wired into the Claude Code *agent session*
that authored this file — it is not reachable from the standalone Railway
process at runtime, so calling it here would silently fail or crash forever.

Per the no-fake-data rule: rather than fabricate a "ctrader" source that isn't
actually wired up server-side, this collector is honest about using FMP (a real,
live data source already powering the rest of AURUM-X) until the OAuth client
lands. `source` always reflects what *actually* served the price.
"""
from services.redis_service import cache_get, cache_set
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CTraderCollector:
    """
    Fetches live XAUUSD price. Cached 30 seconds — live price, fast refresh.
    Currently backed by FMP (real data); will switch to a direct cTrader
    OAuth2/OpenAPI client once that integration is built.
    """

    async def get_gold_price(self) -> dict:
        cache_key = "ctrader_xauusd_price"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        from collectors.fmp_collector import FMPCollector
        fmp = FMPCollector()
        fmp_price = await fmp.get_gold_price()

        if not fmp_price.get("price"):
            result = {
                "symbol":     "XAUUSD",
                "price":      None,
                "source":     "unavailable",
                "rationale":  "No live price source reachable — FMP returned no data and cTrader OAuth integration is not yet built",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            return result

        result = {
            "symbol":     "XAUUSD",
            "price":      fmp_price.get("price"),
            "source":     "fmp",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        await cache_set(cache_key, result, ttl_seconds=30)
        return result

    async def get_ohlcv(self, timeframe: str = "1h", bars: int = 24) -> list:
        """
        OHLCV bars for XAUUSD. Cached 5 minutes.
        Honest no-data: returns [] until a real bar-data source (cTrader OAuth
        or FMP intraday) is wired up — no synthetic candles.
        """
        cache_key = f"ctrader_xauusd_ohlcv_{timeframe}_{bars}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        result: list = []
        await cache_set(cache_key, result, ttl_seconds=300)
        return result
