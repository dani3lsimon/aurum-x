import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

# Events that directly move gold — highlighted for traders
GOLD_MOVERS = {
    "nonfarm payrolls", "cpi", "pce", "fed", "fomc", "interest rate",
    "gdp", "unemployment", "inflation", "ism", "pmi", "retail sales",
    "jolts", "jobless claims", "treasury", "durable goods",
    "consumer confidence", "housing starts", "industrial production",
    "michigan", "sentiment", "eci", "core", "trade balance",
    "ats", "average hourly", "labor", "wages",
}


def _is_gold_relevant(event_name: str) -> bool:
    name = event_name.lower()
    return any(kw in name for kw in GOLD_MOVERS)


def _fetch_sync(days_ahead: int) -> List[Dict]:
    """
    Synchronous ForexFactory scrape via the economic-calendar library.
    Called inside run_in_executor so it never blocks the event loop.
    """
    from economic_calendar import EconomicCalendar

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    cal    = EconomicCalendar()
    events = cal.get_events(now, end)

    result = []
    for e in events:
        if e.impact.lower() not in ("medium", "high"):
            continue

        # Combine date + time into a single UTC ISO timestamp
        try:
            event_dt = datetime(
                e.date.year, e.date.month, e.date.day,
                e.time.hour if e.time else 0,
                e.time.minute if e.time else 0,
                tzinfo=timezone.utc,
            )
        except Exception:
            continue

        result.append({
            "date":          event_dt.isoformat(),
            "country":       e.country  or "",
            "currency":      e.currency or "",
            "event":         e.event    or "",
            "impact":        e.impact.lower(),
            "actual":        e.actual   if e.actual   not in (None, "") else None,
            "forecast":      e.forecast if e.forecast not in (None, "") else None,
            "previous":      e.previous if e.previous not in (None, "") else None,
            "gold_relevant": _is_gold_relevant(e.event or ""),
        })

    result.sort(key=lambda x: x["date"])
    logger.info(f"[economic_calendar] scraped {len(result)} medium/high-impact events")
    return result


async def fetch_economic_events(days_ahead: int = 7) -> List[Dict]:
    """
    Async wrapper — runs the synchronous ForexFactory scrape in a thread pool
    so it never blocks the FastAPI event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_sync, days_ahead)
