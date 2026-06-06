# backend/collectors/fmp_collector.py
# FMP MCP Connector — NO httpx calls, NO API key, NO HTTP requests.
# All data fetched via the FMP MCP tools injected by the connector.
# This module is called by the backend Python process which has access
# to MCP tool results passed in via the orchestration layer.
#
# Since Python cannot call MCP tools natively at runtime (MCP tools are
# invoked by the Claude Code agent layer), this collector provides:
#   1. A data cache interface populated by the scheduler when the agent runs
#   2. Stub async methods that return cached data written by the MCP layer
#   3. Direct Supabase reads for data the scheduler has already persisted
#
# The FMP MCP tools are called by the Claude agent in task_scheduler.py
# via the _run_fmp_update() job, which writes results to Redis/Supabase.
# These methods then read that cached data.

import json
import logging
from datetime import datetime, timedelta
from services.supabase_service import get_supabase
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)


class FMPCollector:
    """
    Reads FMP data from Redis cache or Supabase.
    Cache is populated by the scheduler's FMP MCP update jobs.
    """

    # ── Gold / Commodities ─────────────────────────────────────────────────

    async def get_gold_price(self) -> dict:
        cached = await cache_get("fmp:gold_price")
        if cached:
            return cached
        # Fallback: read last known price from Supabase
        try:
            sb = get_supabase()
            result = (
                sb.table("gold_prices")
                .select("*")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                row = result.data[0]
                return {
                    "symbol": "XAUUSD",
                    "price": float(row.get("price", 0)),
                    "timestamp": row.get("timestamp"),
                    "source": "supabase_cache",
                }
        except Exception as e:
            logger.warning(f"Gold price Supabase fallback failed: {e}")
        return {"symbol": "XAUUSD", "price": 0, "source": "unavailable"}

    async def get_commodities(self) -> dict:
        cached = await cache_get("fmp:commodities")
        return cached or {}

    # ── Treasury Yields ────────────────────────────────────────────────────

    async def get_treasury_yields(self) -> dict:
        cached = await cache_get("fmp:treasury_yields")
        if cached:
            return cached
        # Fallback: Supabase yield_data table
        try:
            sb = get_supabase()
            result = (
                sb.table("yield_data")
                .select("*")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            logger.warning(f"Yield Supabase fallback failed: {e}")
        return {}

    # ── Forex / Currency ───────────────────────────────────────────────────

    async def get_forex_rates(self) -> dict:
        cached = await cache_get("fmp:forex")
        if cached:
            return cached
        # Fallback: Supabase currency_data table
        try:
            sb = get_supabase()
            result = (
                sb.table("currency_data")
                .select("*")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            logger.warning(f"Forex Supabase fallback failed: {e}")
        return {}

    # ── COT Positioning ────────────────────────────────────────────────────

    async def get_cot_data(self, symbol: str = "XAUUSD") -> dict:
        cached = await cache_get(f"fmp:cot:{symbol}")
        return cached or {}

    # ── Economic Calendar ──────────────────────────────────────────────────

    async def get_economic_calendar(self, days_ahead: int = 7) -> list:
        cached = await cache_get("fmp:economic_calendar")
        if cached:
            return cached
        # Fallback: read from Supabase economic_releases
        try:
            sb = get_supabase()
            now = datetime.utcnow().isoformat()
            future = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat()
            result = (
                sb.table("economic_releases")
                .select("*")
                .gte("release_date", now)
                .lte("release_date", future)
                .order("release_date")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"Calendar Supabase fallback failed: {e}")
        return []

    # ── Financial News ─────────────────────────────────────────────────────

    async def get_financial_news(self, limit: int = 20) -> list:
        cached = await cache_get("fmp:news")
        if cached:
            return cached[:limit]
        # Fallback: read from Supabase news_articles
        try:
            sb = get_supabase()
            result = (
                sb.table("news_articles")
                .select("*")
                .order("published_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"News Supabase fallback failed: {e}")
        return []

    # ── Macro / Economics ──────────────────────────────────────────────────

    async def get_macro_indicators(self) -> dict:
        cached = await cache_get("fmp:macro_indicators")
        return cached or {}

    # ── Cache Write Helpers (called by scheduler after MCP tool results) ───

    async def write_gold_price(self, data: dict):
        await cache_set("fmp:gold_price", data, ttl_seconds=360)

    async def write_forex(self, data: dict):
        await cache_set("fmp:forex", data, ttl_seconds=900)

    async def write_treasury_yields(self, data: dict):
        await cache_set("fmp:treasury_yields", data, ttl_seconds=900)

    async def write_commodities(self, data: dict):
        await cache_set("fmp:commodities", data, ttl_seconds=900)

    async def write_cot(self, symbol: str, data: dict):
        await cache_set(f"fmp:cot:{symbol}", data, ttl_seconds=86400)

    async def write_calendar(self, data: list):
        await cache_set("fmp:economic_calendar", data, ttl_seconds=3600)

    async def write_news(self, data: list):
        await cache_set("fmp:news", data, ttl_seconds=600)

    async def write_macro_indicators(self, data: dict):
        await cache_set("fmp:macro_indicators", data, ttl_seconds=3600)
