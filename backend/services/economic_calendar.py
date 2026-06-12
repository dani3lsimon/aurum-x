"""
Economic calendar — three-source strategy:
  1. FMP (Financial Modeling Prep)  — primary if FMP_API_KEY set; full 4-week calendar
     with actual/forecast/previous for all major currencies.
  2. ForexFactory mirror             — this-week actuals (nextweek/2weeksout feeds
     are broken as of mid-2026; only thisweek.json is live).
  3. FRED                            — confirmed US macro release dates for next 28 days;
     merged on top of FF to fill in the coming weeks.

Source priority:
  FMP (if key set) → FF + FRED merge → FRED-only last resort
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── FMP ───────────────────────────────────────────────────────────────────────
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# FMP uses ISO country codes; map to currency codes for flag display
COUNTRY_TO_CURRENCY: dict[str, str] = {
    "US": "USD", "EU": "EUR", "DE": "EUR", "FR": "EUR", "IT": "EUR",
    "ES": "EUR", "PT": "EUR", "NL": "EUR", "BE": "EUR",
    "GB": "GBP", "JP": "JPY", "CN": "CNY", "CA": "CAD",
    "AU": "AUD", "NZ": "NZD", "CH": "CHF",
}

# ── ForexFactory mirror ───────────────────────────────────────────────────────
FF_BASE  = "https://nfs.faireconomy.media"
FF_WEEKS = ["thisweek"]   # nextweek + 2weeksout return 404 as of Jun 2026

# ── FRED release IDs ─────────────────────────────────────────────────────────
FRED_RELEASES = {
    10:  ("Nonfarm Payrolls (NFP)",          "high"),
    33:  ("CPI",                              "high"),
    21:  ("GDP",                              "high"),
    22:  ("PCE",                              "high"),
    392: ("FOMC Rate Decision",               "high"),
    103: ("Initial Jobless Claims",           "medium"),
    46:  ("Core PCE",                         "high"),
    53:  ("PPI",                              "medium"),
    14:  ("Industrial Production",            "medium"),
    20:  ("Retail Sales",                     "medium"),
    26:  ("Consumer Confidence",              "medium"),
    293: ("Michigan Consumer Sentiment",      "medium"),
    180: ("ISM Manufacturing PMI",            "medium"),
    188: ("ISM Services PMI",                 "medium"),
    84:  ("Durable Goods Orders",             "medium"),
    238: ("JOLTS Job Openings",               "medium"),
    17:  ("Housing Starts",                   "medium"),
    125: ("Trade Balance",                    "medium"),
}

GOLD_MOVERS = {
    "nonfarm payrolls", "cpi", "pce", "fed", "fomc", "interest rate",
    "gdp", "unemployment", "inflation", "ism", "pmi", "retail sales",
    "jolts", "jobless claims", "durable goods", "consumer confidence",
    "housing starts", "industrial production", "michigan", "sentiment",
    "trade balance", "average hourly", "labor", "wages", "core",
    "treasury", "debt", "deficit", "reserve",
}


def _is_gold_relevant(title: str, currency: str = "") -> bool:
    if currency.upper() in ("USD", "EUR"):
        return True
    t = title.lower()
    return any(kw in t for kw in GOLD_MOVERS)


def _clean(val) -> str | None:
    return None if val in (None, "", "—", "-", "N/A") else str(val).strip()


# ── Source 1: FMP ─────────────────────────────────────────────────────────────

async def _fetch_fmp(today: datetime, cutoff: datetime) -> Tuple[List[Dict], list]:
    api_key = os.getenv("FMP_API_KEY", "")
    if not api_key:
        return [], ["FMP: FMP_API_KEY not set — skipped"]

    url = (
        f"{FMP_BASE}/economic_calendar"
        f"?from={today.strftime('%Y-%m-%d')}"
        f"&to={cutoff.strftime('%Y-%m-%d')}"
        f"&apikey={api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()

        if not isinstance(data, list):
            return [], [f"FMP: unexpected response type {type(data)}"]

        events: List[Dict] = []
        seen: set = set()

        for e in data:
            impact = (e.get("impact") or "").capitalize()
            if impact not in ("High", "Medium"):
                continue
            try:
                raw_date = e.get("date", "").replace(" ", "T")
                dt = datetime.fromisoformat(raw_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            except Exception:
                continue
            if dt < today or dt > cutoff:
                continue

            country  = e.get("country", "")
            currency = COUNTRY_TO_CURRENCY.get(country.upper(), country.upper())
            title    = e.get("event", "")
            key      = (dt.isoformat(), title)
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "date":          dt.isoformat(),
                "country":       currency,
                "currency":      currency,
                "event":         title,
                "impact":        impact.lower(),
                "actual":        _clean(e.get("actual")),
                "forecast":      _clean(e.get("estimate")),
                "previous":      _clean(e.get("previous")),
                "gold_relevant": _is_gold_relevant(title, currency),
                "source":        "fmp",
            })

        events.sort(key=lambda x: x["date"])
        return events, [f"FMP: {len(data)} raw → {len(events)} after filter"]

    except Exception as exc:
        logger.warning(f"[calendar] FMP failed: {exc}")
        return [], [f"FMP: FAILED — {exc}"]


# ── Source 2: ForexFactory ────────────────────────────────────────────────────

async def _ff_get_week(client: httpx.AsyncClient, tag: str) -> Tuple[list, str]:
    url = f"{FF_BASE}/ff_calendar_{tag}.json"
    try:
        r = await client.get(url, timeout=10)
        if r.status_code == 404:
            return [], f"{tag}: 404"
        r.raise_for_status()
        data = r.json()
        return data, f"{tag}: {len(data)} raw"
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
                "gold_relevant": _is_gold_relevant(title, e.get("country", "")),
                "source":        "forexfactory",
            })

    diag.append(f"FF total after filter: {len(events)}")
    return events, diag


# ── Source 3: FRED ────────────────────────────────────────────────────────────

async def _fetch_fred(today: datetime, cutoff: datetime) -> Tuple[List[Dict], list]:
    api_key = os.getenv("FRED_API_KEY", "")
    if not api_key:
        return [], ["FRED: no FRED_API_KEY — skipped"]

    events: List[Dict] = []
    diag = []

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [
            client.get(
                f"https://api.stlouisfed.org/fred/release/dates"
                f"?release_id={rid}"
                f"&realtime_start={today.strftime('%Y-%m-%d')}"
                f"&realtime_end={cutoff.strftime('%Y-%m-%d')}"
                f"&api_key={api_key}&file_type=json"
                f"&include_release_dates_with_no_data=true",
                timeout=10,
            )
            for rid in FRED_RELEASES
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    rids = list(FRED_RELEASES.keys())
    for i, resp in enumerate(responses):
        rid = rids[i]
        name, impact = FRED_RELEASES[rid]
        if isinstance(resp, Exception):
            diag.append(f"FRED {rid}: FAILED — {resp}")
            continue
        try:
            for d in resp.json().get("release_dates", []):
                date_str = d.get("date", "")
                if not date_str:
                    continue
                y, mo, dy = (int(x) for x in date_str.split("-"))
                # FOMC released at 14:00 ET = 18:00 UTC; others 08:30 ET = 13:30 UTC
                hour = 18 if rid == 392 else 13
                minute = 0 if rid == 392 else 30
                dt = datetime(y, mo, dy, hour, minute, tzinfo=timezone.utc)
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
            diag.append(f"FRED {rid} parse: {exc}")

    diag.append(f"FRED total: {len(events)}")
    return events, diag


# ── Public entry point ────────────────────────────────────────────────────────

async def fetch_economic_events(days_ahead: int = 28) -> Tuple[List[Dict], dict]:
    """
    Returns (events_list, diagnostics_dict).
    Priority: FMP (if key set) → FF this-week actuals merged with FRED future dates.
    """
    now    = datetime.now(timezone.utc)
    today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today + timedelta(days=days_ahead)

    # ── Try FMP first ────────────────────────────────────────────────────────
    fmp_events, fmp_diag = await _fetch_fmp(today, cutoff)
    if fmp_events:
        logger.info(f"[calendar] FMP: {len(fmp_events)} events")
        return fmp_events, {"source": "fmp", "fmp": fmp_diag}

    # ── Merge FF (this week) + FRED (next 28 days) ───────────────────────────
    (ff_events, ff_diag), (fred_events, fred_diag) = await asyncio.gather(
        _fetch_forexfactory(today, cutoff),
        _fetch_fred(today, cutoff),
    )

    # FF events take priority; FRED fills in dates that FF doesn't cover
    ff_date_set = {e["date"][:10] for e in ff_events}
    merged = list(ff_events)
    added_fred = 0
    seen_fred: set = set()
    for fe in fred_events:
        date_key = fe["date"][:10]
        dedup_key = (date_key, fe["event"])
        if date_key not in ff_date_set and dedup_key not in seen_fred:
            merged.append(fe)
            seen_fred.add(dedup_key)
            added_fred += 1

    merged.sort(key=lambda x: x["date"])
    logger.info(
        f"[calendar] FF+FRED merge: {len(ff_events)} FF + {added_fred} FRED → {len(merged)} total"
    )

    if merged:
        return merged, {"source": "ff+fred", "ff": ff_diag, "fred": fred_diag}

    # ── Nothing from any source ──────────────────────────────────────────────
    logger.error("[calendar] All sources returned 0 events")
    return [], {"source": "none", "fmp": fmp_diag, "ff": ff_diag, "fred": fred_diag}
