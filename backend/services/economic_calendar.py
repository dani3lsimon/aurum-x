import os
import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Events that directly move gold — used to flag high relevance rows
GOLD_MOVERS = {
    "nonfarm payrolls", "cpi", "pce", "fed", "fomc", "interest rate",
    "gdp", "unemployment", "inflation", "ism", "pmi", "retail sales",
    "jolts", "jobless claims", "treasury", "debt ceiling", "durable goods",
    "consumer confidence", "housing starts", "industrial production",
    "michigan sentiment", "eci", "core", "trade balance",
}


def _is_gold_relevant(event_name: str) -> bool:
    name = event_name.lower()
    return any(kw in name for kw in GOLD_MOVERS)


async def fetch_economic_events(days_ahead: int = 7) -> List[Dict]:
    """
    Fetch medium + high impact economic events from Finnhub.
    Returns list sorted by date ascending; each event has a gold_relevant flag.
    Cached by the caller — this function always hits the API.
    """
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY not set")

    now  = datetime.now(timezone.utc)
    end  = now + timedelta(days=days_ahead)
    params = {
        "from":  now.strftime("%Y-%m-%d"),
        "to":    end.strftime("%Y-%m-%d"),
        "token": api_key,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{FINNHUB_BASE}/calendar/economic", params=params)
        resp.raise_for_status()
        data = resp.json()

    events = data.get("economicCalendar", [])

    # Keep only medium and high impact; sort ascending by date
    filtered = [e for e in events if e.get("impact") in ("medium", "high")]
    filtered.sort(key=lambda e: e.get("time") or e.get("date") or "")

    # Normalise fields and add gold_relevant flag
    result = []
    for e in filtered:
        result.append({
            "date":         e.get("time") or e.get("date"),   # ISO string from Finnhub
            "country":      e.get("country", ""),
            "currency":     e.get("currency", ""),
            "event":        e.get("event", ""),
            "impact":       e.get("impact", "medium"),
            "actual":       e.get("actual"),
            "forecast":     e.get("estimate"),
            "previous":     e.get("prev"),
            "gold_relevant": _is_gold_relevant(e.get("event", "")),
        })

    logger.info(f"[economic_calendar] fetched {len(result)} medium/high-impact events")
    return result
