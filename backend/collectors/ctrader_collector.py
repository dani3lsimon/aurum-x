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
    Backed by OANDA's v20 REST API (real broker bid/ask/spread) — replaces
    the previous FMP-stub fallback now that a direct broker feed is wired up.
    cTrader OAuth2/OpenAPI integration remains a future option (kept for
    the MCP connector — see ibkr.env / ctrader credentials in .env).
    """

    async def get_gold_price(self) -> dict:
        from collectors.oanda_collector import OandaCollector
        return await OandaCollector().get_gold_price()

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
