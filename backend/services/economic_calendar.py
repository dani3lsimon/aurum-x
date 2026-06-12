"""
Economic calendar via ForexFactory's public JSON feed.
No API key required — uses nfs.faireconomy.media which serves
the same data as the ForexFactory calendar page.
httpx is already in requirements.txt; no new dependencies needed.
"""
import asyncio
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import httpx

logger = logging.getLogger(__name__)

FF_BASE = "https://nfs.faireconomy.media"

IMPACT_MAP = {"High": "high", "Medium": "medium", "Low": "low", "Holiday": "low"}

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


def _parse_dt(date_str: str, time_str: str) -> datetime | None:
    """
    ForexFactory format:
      date: "06-13-2025" (MM-DD-YYYY)
      time: "8:30am" | "12:00pm" | "All Day" | "Tentative" | ""
    Returns a UTC-aware datetime or None on parse failure.
    """
    try:
        dt_date = datetime.strptime(date_str.strip(), "%m-%d-%Y").date()
    except ValueError:
        return None

    t = time_str.strip().lower()
    h, m = 0, 0
    if t not in ("", "all day", "tentative"):
        match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", t)
        if match:
            h, m, ampm = int(match.group(1)), int(match.group(2)), match.group(3)
            if ampm == "pm" and h != 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0

    return datetime(dt_date.year, dt_date.month, dt_date.day, h, m, tzinfo=timezone.utc)


def _blank(val) -> bool:
    return val in (None, "", "—", "-")


async def _get_week(client: httpx.AsyncClient, tag: str) -> list:
    try:
        r = await client.get(f"{FF_BASE}/ff_calendar_{tag}.json", timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning(f"[economic_calendar] {tag} fetch failed: {exc}")
        return []


async def fetch_economic_events(days_ahead: int = 7) -> List[Dict]:
    """
    Returns medium + high impact events in the next `days_ahead` days,
    sorted by datetime ascending. Each event has a gold_relevant flag.
    """
    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(days=days_ahead)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AurumX/1.0)"}
    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        this_week, next_week = await asyncio.gather(
            _get_week(client, "thisweek"),
            _get_week(client, "nextweek"),
        )

    result: List[Dict] = []
    seen:   set        = set()

    for raw in (this_week + next_week):
        impact = IMPACT_MAP.get(raw.get("impact", ""), "")
        if impact not in ("medium", "high"):
            continue

        dt = _parse_dt(raw.get("date", ""), raw.get("time", ""))
        if dt is None:
            continue
        if dt < now - timedelta(minutes=5) or dt > cutoff:
            continue

        key = (dt.isoformat(), raw.get("title", ""))
        if key in seen:
            continue
        seen.add(key)

        result.append({
            "date":          dt.isoformat(),
            "country":       raw.get("country", ""),
            "currency":      raw.get("country", ""),   # FF uses country as the currency code
            "event":         raw.get("title", ""),
            "impact":        impact,
            "actual":        None if _blank(raw.get("actual"))   else raw.get("actual"),
            "forecast":      None if _blank(raw.get("forecast")) else raw.get("forecast"),
            "previous":      None if _blank(raw.get("previous")) else raw.get("previous"),
            "gold_relevant": _is_gold_relevant(raw.get("title", "")),
        })

    result.sort(key=lambda x: x["date"])
    logger.info(f"[economic_calendar] {len(result)} medium/high events over next {days_ahead} days")
    return result
