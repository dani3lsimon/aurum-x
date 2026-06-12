"""
Economic calendar via ForexFactory's public JSON feed (nfs.faireconomy.media).
No API key, no extra dependencies — httpx is already in requirements.txt.

Actual feed format (discovered empirically):
  { "title": "...", "country": "USD", "date": "2026-06-12T08:30:00-04:00",
    "impact": "High", "forecast": "...", "previous": "...", "actual": "" }

nextweek endpoint returns 404 on Thursdays/Fridays when not yet published;
we fall back gracefully so at minimum thisweek always shows.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import httpx

logger = logging.getLogger(__name__)

FF_BASE    = "https://nfs.faireconomy.media"
FF_WEEKS   = ["thisweek", "nextweek", "2weeksout"]   # try in order; 404s are fine

GOLD_MOVERS = {
    "nonfarm payrolls", "cpi", "pce", "fed", "fomc", "interest rate",
    "gdp", "unemployment", "inflation", "ism", "pmi", "retail sales",
    "jolts", "jobless claims", "durable goods", "consumer confidence",
    "housing starts", "industrial production", "michigan", "sentiment",
    "trade balance", "average hourly", "labor", "wages", "core",
    "treasury", "debt", "deficit", "reserve",
}


def _is_gold_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in GOLD_MOVERS)


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ISO 8601 date string with offset → UTC-aware datetime."""
    try:
        dt = datetime.fromisoformat(date_str.strip())
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _clean(val) -> str | None:
    return None if val in (None, "", "—", "-", "N/A") else str(val).strip()


async def _get_week(client: httpx.AsyncClient, tag: str) -> list:
    try:
        r = await client.get(f"{FF_BASE}/ff_calendar_{tag}.json", timeout=12)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning(f"[economic_calendar] {tag} fetch failed: {exc}")
        return []


async def fetch_economic_events(days_ahead: int = 7) -> List[Dict]:
    """
    Returns medium + high impact events from start-of-today through
    `days_ahead` days ahead, sorted ascending. Each row has gold_relevant flag.
    """
    now    = datetime.now(timezone.utc)
    # Show from beginning of today UTC so we don't miss events that started
    # earlier today but still have relevant data (actual / forecast populated).
    today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today + timedelta(days=days_ahead)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AurumX/1.0)"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        weeks = await asyncio.gather(*[_get_week(client, tag) for tag in FF_WEEKS])

    seen:   set        = set()
    result: List[Dict] = []

    for raw_list in weeks:
        for e in raw_list:
            impact = e.get("impact", "")
            if impact not in ("High", "Medium"):
                continue

            dt = _parse_iso(e.get("date", ""))
            if dt is None or dt < today or dt > cutoff:
                continue

            title = e.get("title", "")
            key   = (dt.isoformat(), title)
            if key in seen:
                continue
            seen.add(key)

            result.append({
                "date":          dt.isoformat(),
                "country":       e.get("country", ""),
                "currency":      e.get("country", ""),
                "event":         title,
                "impact":        impact.lower(),
                "actual":        _clean(e.get("actual")),
                "forecast":      _clean(e.get("forecast")),
                "previous":      _clean(e.get("previous")),
                "gold_relevant": _is_gold_relevant(title),
            })

    result.sort(key=lambda x: x["date"])
    total = len(result)
    gold  = sum(1 for e in result if e["gold_relevant"])
    logger.info(f"[economic_calendar] {total} events ({gold} gold-relevant) over next {days_ahead} days")
    return result
