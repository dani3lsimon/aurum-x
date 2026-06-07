# backend/collectors/news_collector.py
# Primary: free RSS feeds (no tier lock — FMP news/calendar requires a paid plan
# and returns null on the current tier). Fallback: Finnhub REST API.
# Honest no-data: if every feed fails, methods return [] — never fabricated headlines.
import asyncio
import re
import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from config import get_settings
from collectors.fmp_collector import FMPCollector
from services.redis_service import cache_get, cache_set
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
settings = get_settings()
FINNHUB_BASE = "https://finnhub.io/api/v1"
RSS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AURUM-X/3.0)"}

# Verified working feeds — gold/macro-relevant + general/geopolitical wires.
# (Kitco's RSS endpoints are dead — 404/redirect — so dropped in favour of these.)
RSS_FEEDS = [
    {"url": "https://www.fxstreet.com/rss/news?category=commodities", "weight": 3, "tag": "gold"},
    {"url": "https://www.mining.com/feed/",                            "weight": 3, "tag": "gold"},
    {"url": "https://www.investing.com/rss/news_11.rss",               "weight": 3, "tag": "gold"},
    {"url": "https://www.marketwatch.com/rss/topstories",              "weight": 2, "tag": "macro"},
    {"url": "https://finance.yahoo.com/news/rssindex",                 "weight": 2, "tag": "macro"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",             "weight": 1, "tag": "geo"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",  "weight": 1, "tag": "geo"},
]

GOLD_MACRO_KEYWORDS = [
    "gold", "xau", "silver", "bullion", "fed", "federal reserve", "interest rate",
    "inflation", "cpi", "treasury", "yield", "dollar", "dxy", "powell", "rate cut",
    "rate hike", "recession", "jobs report", "payrolls", "fomc", "central bank",
]

GEO_KEYWORDS = [
    "war", "sanction", "tariff", "trade war", "conflict", "military", "missile",
    "nato", "china", "russia", "iran", "israel", "ukraine", "nuclear", "crude",
    "opec", "energy crisis", "escalation", "invasion", "ceasefire", "weapons",
    "geopolit", "taiwan", "north korea",
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


class NewsCollector:

    def __init__(self):
        self.fmp = FMPCollector()

    # ── RSS Primary ────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _fetch_rss_feed(self, feed: dict) -> list:
        async with httpx.AsyncClient(timeout=10, headers=RSS_HEADERS, follow_redirects=True) as client:
            resp = await client.get(feed["url"])
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

        items = []
        # RSS 2.0 uses <item>, Atom uses <entry> — handle both.
        for node in root.iter():
            tag = node.tag.split("}")[-1]  # strip XML namespace
            if tag not in ("item", "entry"):
                continue
            title = description = link = pub_date = ""
            for child in node:
                ctag = child.tag.split("}")[-1]
                if ctag == "title":
                    title = _strip_html(child.text or "")
                elif ctag in ("description", "summary", "content"):
                    description = _strip_html(child.text or "")
                elif ctag == "link":
                    link = (child.text or child.attrib.get("href", "")).strip()
                elif ctag in ("pubDate", "published", "updated"):
                    pub_date = (child.text or "").strip()
            if title:
                items.append({
                    "title": title,
                    "text": description,
                    "url": link,
                    "publishedDate": pub_date,
                    "site": feed["url"],
                    "weight": feed["weight"],
                    "tag": feed["tag"],
                })
        return items

    async def _fetch_all_feeds(self) -> list:
        results = await asyncio.gather(
            *(self._fetch_rss_feed(f) for f in RSS_FEEDS),
            return_exceptions=True,
        )
        all_items = []
        for feed, result in zip(RSS_FEEDS, results):
            if isinstance(result, Exception):
                logger.warning(f"RSS feed failed [{feed['url']}]: {result}")
                continue
            all_items.extend(result)

        # De-dupe by title, keep highest-weight feed's copy, sort by weight desc.
        seen = {}
        for item in all_items:
            key = item["title"].lower()
            if key not in seen or item["weight"] > seen[key]["weight"]:
                seen[key] = item
        return sorted(seen.values(), key=lambda x: x["weight"], reverse=True)

    @staticmethod
    def _matches(item: dict, keywords: list) -> bool:
        haystack = f"{item.get('title', '')} {item.get('text', '')}".lower()
        return any(kw in haystack for kw in keywords)

    async def get_recent_news(self, category: str = "general") -> list:
        cache_key = "news:recent_rss"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            items = await self._fetch_all_feeds()
            relevant = [i for i in items if self._matches(i, GOLD_MACRO_KEYWORDS)]
            # If too few gold/macro-specific hits, top up with general headlines
            # from the higher-weight feeds rather than returning a near-empty list.
            if len(relevant) < 8:
                seen_titles = {i["title"] for i in relevant}
                relevant += [i for i in items if i["title"] not in seen_titles][:8 - len(relevant)]
            result = relevant[:20]
            if result:
                await cache_set(cache_key, result, ttl_seconds=600)
            else:
                logger.warning("RSS news: all feeds returned zero usable items, falling back to Finnhub")
                result = await self._finnhub_news(category)
            return result
        except Exception as e:
            logger.warning(f"RSS news failed, falling back to Finnhub: {e}")
            return await self._finnhub_news(category)

    async def get_geopolitical_news(self) -> list:
        cache_key = "news:geo_rss"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            items = await self._fetch_all_feeds()
            filtered = [i for i in items if self._matches(i, GEO_KEYWORDS)]
            result = filtered[:15]
            if result:
                await cache_set(cache_key, result, ttl_seconds=600)
            else:
                logger.warning("RSS geo news: zero geo-relevant items, falling back to Finnhub")
                result = await self._finnhub_geo_news()
            return result
        except Exception as e:
            logger.warning(f"RSS geo news failed, falling back to Finnhub: {e}")
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
            filtered = [
                item for item in data
                if any(kw in item.get("headline", "").lower() for kw in GEO_KEYWORDS)
            ]
            return filtered[:15]
        except Exception as e:
            logger.error(f"Finnhub geo fallback failed: {e}")
            return []

    async def _finnhub_calendar(self) -> list:
        from datetime import timedelta
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        next_week = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            data = await self._finnhub_fetch(
                "calendar/economic", {"from": today, "to": next_week}
            )
            events = data.get("economicCalendar", [])
            return [e for e in events if e.get("impact") in ["high", "medium"]][:20]
        except Exception as e:
            logger.error(f"Finnhub calendar fallback failed: {e}")
            return []
