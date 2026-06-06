# backend/collectors/news_collector.py
# Primary: FMP MCP connector
# Fallback: Finnhub REST API
import httpx
import logging
from config import get_settings
from collectors.fmp_collector import FMPCollector
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
settings = get_settings()
FINNHUB_BASE = "https://finnhub.io/api/v1"


class NewsCollector:

    def __init__(self):
        self.fmp = FMPCollector()

    # ── FMP Primary ────────────────────────────────────────────────────────

    async def get_recent_news(self, category: str = "general") -> list:
        try:
            return await self.fmp.get_financial_news(limit=20)
        except Exception as e:
            logger.warning(f"FMP news failed, falling back to Finnhub: {e}")
            return await self._finnhub_news(category)

    async def get_geopolitical_news(self) -> list:
        try:
            all_news = await self.fmp.get_financial_news(limit=50)
            geo_keywords = [
                "war", "sanction", "tariff", "trade", "conflict", "military",
                "nato", "china", "russia", "iran", "israel", "nuclear",
                "crude", "opec", "energy", "federal reserve", "treasury",
                "escalation", "invasion", "ceasefire", "weapons", "geopolit"
            ]
            filtered = [
                item for item in all_news
                if any(kw in str(item.get("title", "")).lower() or
                       kw in str(item.get("text", "")).lower()
                       for kw in geo_keywords)
            ]
            return filtered[:15]
        except Exception as e:
            logger.warning(f"FMP geo news failed, falling back to Finnhub: {e}")
            return await self._finnhub_geo_news()

    async def get_economic_calendar(self) -> list:
        try:
            return await self.fmp.get_economic_calendar()
        except Exception as e:
            logger.warning(f"FMP calendar failed, falling back to Finnhub: {e}")
            return await self._finnhub_calendar()

    # ── Finnhub Fallback ───────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    async def _finnhub_fetch(self, endpoint: str, params: dict) -> dict:
        params["token"] = settings.finnhub_api_key
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{FINNHUB_BASE}/{endpoint}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def _finnhub_news(self, category: str = "general") -> list:
        try:
            data = await self._finnhub_fetch("news", {"category": category})
            return data[:20] if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Finnhub news fallback failed: {e}")
            return []

    async def _finnhub_geo_news(self) -> list:
        try:
            data = await self._finnhub_fetch("news", {"category": "general"})
            if not isinstance(data, list):
                return []
            geo_keywords = [
                "war", "sanction", "tariff", "conflict", "military",
                "nato", "china", "russia", "iran", "israel", "nuclear",
                "escalation", "invasion"
            ]
            filtered = [
                item for item in data
                if any(kw in item.get("headline", "").lower() for kw in geo_keywords)
            ]
            return filtered[:15]
        except Exception as e:
            logger.error(f"Finnhub geo fallback failed: {e}")
            return []

    async def _finnhub_calendar(self) -> list:
        from datetime import datetime, timedelta
        today = datetime.utcnow().strftime("%Y-%m-%d")
        next_week = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            data = await self._finnhub_fetch(
                "calendar/economic", {"from": today, "to": next_week}
            )
            events = data.get("economicCalendar", [])
            return [e for e in events if e.get("impact") in ["high", "medium"]][:20]
        except Exception as e:
            logger.error(f"Finnhub calendar fallback failed: {e}")
            return []
