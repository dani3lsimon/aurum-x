"""
Economic calendar — two-source strategy:
  Primary:  ForexFactory JSON feed via nfs.faireconomy.media (free, no key)
  Fallback: FRED release calendar (US macro only, but always reachable)

Returns (events, diagnostics) so the caller can expose fetch errors.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

import httpx

logger = logging.getLogger(__name__)

FF_BASE  = "https://nfs.faireconomy.media"
FF_WEEKS = ["thisweek", "nextweek", "2weeksout"]

GOLD_MOVERS = {
    "nonfarm payrolls", "cpi", "pce", "fed", "fomc", "interest rate",
    "gdp", "unemployment", "inflation", "ism", "pmi", "retail sales",
    "jolts", "jobless claims", "durable goods", "consumer confidence",
    "housing starts", "industrial production", "michigan", "sentiment",
    "trade balance", "average hourly", "labor", "wages", "core",
    "treasury", "debt", "deficit", "reserve",
}

# FRED release IDs for the most gold-relevant US macro series
FRED_RELEASES = {
    10:  ("Nonfarm Payrolls (NFP)",          "high"),
    33:  ("CPI",                              "high"),
    21:  ("GDP",                              "high"),
    22:  ("PCE",                              "high"),
    103: ("Initial Jobless Claims",           "medium"),
    46:  ("Core PCE",                         "high"),
    53:  ("PPI",                              "medium"),
    14:  ("Industrial Production",            "medium"),
    20:  ("Retail Sales",                     "medium"),
    26:  ("Consumer Confidence (Conference)", "medium"),
    293: ("Michigan Consumer Sentiment",      "medium"),
    180: ("ISM Manufacturing PMI",            "medium"),
    188: ("ISM Services PMI",                 "medium"),
}


def _is_gold_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in GOLD_MOVERS)


def _clean(val) -> str | None:
    return None if val in (None, "", "—", "-", "N/A") else str(val).strip()


# ── ForexFactory source ────────────────────────────────────────────────────

async def _ff_get_week(client: httpx.AsyncClient, tag: str) -> Tuple[list, str]:
    url = f"{FF_BASE}/ff_calendar_{tag}.json"
    try:
        r = await client.get(url, timeout=10)
        if r.status_code == 404:
            return [], f"{tag}: 404 (not yet published)"
        r.raise_for_status()
        data = r.json()
        return data, f"{tag}: {len(data)} raw events"
    except Exception as exc:
        return [], f"{tag}: FAILED — {exc}"


async def _fetch_forexfactory(today: datetime, cutoff: datetime) -> Tuple[List[Dict], list]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AurumX/1.0)"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        results = await asyncio.gather(*[_ff_get_week(client, tag) for tag in FF_WEEKS])

    diag = []
    seen: set = set()
    events: List[Dict] = []

    for week_events, note in results:
        diag.append(note)
        for e in week_events:
            if e.get("impact") not in ("High", "Medium"):
                continue
            try:
                dt = datetime.fromisoformat(e["date"].strip()).astimezone(timezone.utc)
            except Exception:
                continue
            if dt < today or dt > cutoff:
                continue
            title = e.get("title", "")
            key = (dt.isoformat(), title)
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "date":          dt.isoformat(),
                "country":       e.get("country", ""),
                "currency":      e.get("country", ""),
                "event":         title,
                "impact":        e["impact"].lower(),
                "actual":        _clean(e.get("actual")),
                "forecast":      _clean(e.get("forecast")),
                "previous":      _clean(e.get("previous")),
                "gold_relevant": _is_gold_relevant(title),
                "source":        "forexfactory",
            })

    diag.append(f"FF total after filter: {len(events)} events")
    return events, diag


# ── FRED fallback source ───────────────────────────────────────────────────

async def _fetch_fred(today: datetime, cutoff: datetime) -> Tuple[List[Dict], list]:
    api_key = os.getenv("FRED_API_KEY", "")
    if not api_key:
        return [], ["FRED: no FRED_API_KEY — skipped"]

    events: List[Dict] = []
    diag = []

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = []
        for rid in FRED_RELEASES:
            url = (
                f"https://api.stlouisfed.org/fred/release/dates"
                f"?release_id={rid}"
                f"&realtime_start={today.strftime('%Y-%m-%d')}"
                f"&realtime_end={cutoff.strftime('%Y-%m-%d')}"
                f"&api_key={api_key}&file_type=json&include_release_dates_with_no_data=true"
            )
            tasks.append(client.get(url, timeout=10))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

    rids = list(FRED_RELEASES.keys())
    for i, resp in enumerate(responses):
        rid = rids[i]
        name, impact = FRED_RELEASES[rid]
        if isinstance(resp, Exception):
            diag.append(f"FRED release {rid}: FAILED — {resp}")
            continue
        try:
            data = resp.json()
            dates = data.get("release_dates", [])
            for d in dates:
                date_str = d.get("date", "")
                if not date_str:
                    continue
                dt = datetime(
                    *[int(x) for x in date_str.split("-")],
                    8, 30,   # assume 8:30 ET → 13:30 UTC (typical US release time)
                    tzinfo=timezone.utc
                )
                if dt < today or dt > cutoff:
                    continue
                events.append({
                    "date":          dt.isoformat(),
                    "country":       "USD",
                    "currency":      "USD",
                    "event":         name,
                    "impact":        impact,
                    "actual":        None,
                    "forecast":      None,
                    "previous":      None,
                    "gold_relevant": True,
                    "source":        "fred",
                })
        except Exception as exc:
            diag.append(f"FRED release {rid} parse error: {exc}")

    diag.append(f"FRED total: {len(events)} events")
    return events, diag


# ── Public entry point ─────────────────────────────────────────────────────

async def fetch_economic_events(days_ahead: int = 7) -> Tuple[List[Dict], dict]:
    """
    Returns (events_list, diagnostics_dict).
    Tries ForexFactory first; if it returns nothing, falls back to FRED.
    """
    now    = datetime.now(timezone.utc)
    today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today + timedelta(days=days_ahead)

    ff_events, ff_diag = await _fetch_forexfactory(today, cutoff)

    if ff_events:
        ff_events.sort(key=lambda x: x["date"])
        logger.info(f"[calendar] FF: {len(ff_events)} events")
        return ff_events, {"source": "forexfactory", "ff": ff_diag}

    # FF returned nothing — try FRED
    logger.warning(f"[calendar] FF returned 0 events — falling back to FRED. Diag: {ff_diag}")
    fred_events, fred_diag = await _fetch_fred(today, cutoff)
    fred_events.sort(key=lambda x: x["date"])
    # Deduplicate by (date, event)
    seen: set = set()
    deduped = []
    for e in fred_events:
        k = (e["date"][:10], e["event"])
        if k not in seen:
            seen.add(k)
            deduped.append(e)

    logger.info(f"[calendar] FRED fallback: {len(deduped)} events")
    return deduped, {"source": "fred_fallback", "ff": ff_diag, "fred": fred_diag}
