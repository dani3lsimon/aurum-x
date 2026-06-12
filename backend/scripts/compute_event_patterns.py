"""
compute_event_patterns.py
─────────────────────────
Weekly cron job — computes historical XAUUSD reaction patterns per event type
and upserts results into Supabase `event_patterns` table.

Data sources
  • FRED API  — historical release dates (free, no scraping)
  • OANDA     — M5 candles for the ±12h window around each release

Run manually:
  cd backend && python scripts/compute_event_patterns.py

Cron (every Monday 06:00 UTC):
  0 6 * * 1 cd /home/opc/backend && python scripts/compute_event_patterns.py >> /var/log/event_patterns.log 2>&1
"""
import os
import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from oandapyV20.exceptions import V20Error
from supabase import create_client
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("event_patterns")

# ── Config ────────────────────────────────────────────────────────────────
OANDA_TOKEN       = os.environ["OANDA_API_TOKEN"]
OANDA_ACCT        = os.environ["OANDA_ACCOUNT_ID"]
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
FRED_API_KEY      = os.environ.get("FRED_API_KEY", "")

INSTRUMENT        = "XAU_USD"
GRANULARITY       = "M5"
LOOKBACK_DAYS     = 730        # 2 years
WINDOW_BEFORE_H   = 12
WINDOW_AFTER_H    = 6
MAX_RETRIES       = 3
SLEEP_S           = 0.35       # rate-limit OANDA

api      = oandapyV20.API(access_token=OANDA_TOKEN, environment="practice")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Event type rules (must mirror frontend normalizeEventType exactly) ────
EVENT_TYPE_RULES: list[tuple[str, list[str], int]] = [
    # (label, keywords, FRED release_id)
    ("CPI",              ["cpi", "consumer price"],                      33),
    ("NFP",              ["nonfarm", "non-farm", "nfp", "employment"],   10),
    ("FOMC",             ["fomc", "federal funds", "interest rate"],     392),
    ("GDP",              ["gdp"],                                        21),
    ("PCE",              ["pce", "personal consumption"],                22),
    ("PPI",              ["ppi", "producer price"],                      62),
    ("Retail Sales",     ["retail sales"],                               56),
    ("ISM Manufacturing",["ism manufacturing"],                          106),
    ("ISM Services",     ["ism services", "ism non-manufacturing"],      244),
    ("Jobless Claims",   ["initial jobless", "unemployment claims"],     103),
]

FRED_RELEASES = {label: rid for label, _, rid in EVENT_TYPE_RULES}


def normalize_event_type(name: str) -> Optional[str]:
    n = name.lower()
    for label, keywords, _ in EVENT_TYPE_RULES:
        if any(kw in n for kw in keywords):
            return label
    return None


# ── FRED: fetch historical release dates ─────────────────────────────────

def get_fred_dates(release_id: int, start: datetime, end: datetime) -> list[datetime]:
    if not FRED_API_KEY:
        log.warning("FRED_API_KEY not set — skipping FRED")
        return []
    url = "https://api.stlouisfed.org/fred/release/dates"
    params = {
        "release_id": release_id,
        "realtime_start": start.strftime("%Y-%m-%d"),
        "realtime_end":   end.strftime("%Y-%m-%d"),
        "api_key":        FRED_API_KEY,
        "file_type":      "json",
        "include_release_dates_with_no_data": "true",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        dates = r.json().get("release_dates", [])
        # Most US macro releases at 08:30 ET = 13:30 UTC
        result = []
        for d in dates:
            raw = d.get("date", "")
            if not raw:
                continue
            try:
                y, mo, dy = (int(x) for x in raw.split("-"))
                result.append(datetime(y, mo, dy, 13, 30, tzinfo=timezone.utc))
            except ValueError:
                continue
        return result
    except Exception as exc:
        log.warning("FRED release %d failed: %s", release_id, exc)
        return []


# ── OANDA candles ─────────────────────────────────────────────────────────

def get_candles(from_dt: datetime, to_dt: datetime) -> Optional[pd.DataFrame]:
    params = {
        "from":        from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to":          to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "granularity": GRANULARITY,
        "price":       "M",
    }
    req = instruments.InstrumentsCandles(instrument=INSTRUMENT, params=params)
    resp = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = api.request(req)
            break
        except V20Error as exc:
            log.warning("OANDA attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                return None
            time.sleep(SLEEP_S * attempt)

    rows = [
        {"time": pd.to_datetime(c["time"]), "close": float(c["mid"]["c"])}
        for c in (resp or {}).get("candles", [])
        if c.get("complete")
    ]
    if len(rows) < 10:
        return None
    return pd.DataFrame(rows).set_index("time")


def nearest_close(df: pd.DataFrame, t: datetime) -> Optional[float]:
    if t < df.index[0] or t > df.index[-1]:
        return None
    idx = df.index.get_indexer([t], method="nearest")[0]
    return float(df.iloc[idx]["close"])


def direction(v: Optional[float]) -> str:
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "down"


def analyze_event(event_dt: datetime, df: pd.DataFrame) -> Optional[dict]:
    def ret(s_min: int, e_min: int) -> Optional[float]:
        p0 = nearest_close(df, event_dt + timedelta(minutes=s_min))
        p1 = nearest_close(df, event_dt + timedelta(minutes=e_min))
        if p0 is None or p1 is None or p0 == 0:
            return None
        return (p1 - p0) / p0 * 100

    windows = {
        "pre_15m":  (-15, 0),
        "pre_1h":   (-60, 0),
        "post_5m":  (0,   5),
        "post_15m": (0,  15),
        "post_30m": (0,  30),
        "post_1h":  (0,  60),
    }
    vals = {k: ret(s, e) for k, (s, e) in windows.items()}
    return {
        "pre_15m_dir": direction(vals["pre_15m"]),
        "pre_1h_dir":  direction(vals["pre_1h"]),
        "react_dir":   direction(vals["post_5m"]),
        "post_15m":    vals["post_15m"],
        "post_30m":    vals["post_30m"],
        "post_1h":     vals["post_1h"],
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=LOOKBACK_DAYS)

    type_stats: dict = defaultdict(lambda: {
        "total":         0,
        "pre15_valid":   0, "pre15_opp": 0,
        "pre1h_valid":   0, "pre1h_opp": 0,
        "post15_list":   [],
        "post30_list":   [],
        "post1h_list":   [],
    })

    for label, _, release_id in EVENT_TYPE_RULES:
        dates = get_fred_dates(release_id, start_dt, end_dt)
        log.info("%-20s  %d historical release dates (FRED id=%d)", label, len(dates), release_id)

        for event_dt in dates:
            from_t = event_dt - timedelta(hours=WINDOW_BEFORE_H)
            to_t   = event_dt + timedelta(hours=WINDOW_AFTER_H)

            df = get_candles(from_t, to_t)
            time.sleep(SLEEP_S)

            if df is None:
                log.debug("  skip %s — no candles", event_dt.date())
                continue

            res = analyze_event(event_dt, df)
            if res is None:
                continue

            st = type_stats[label]
            st["total"] += 1

            if res["pre_15m_dir"] != "flat" and res["react_dir"] != "flat":
                st["pre15_valid"] += 1
                if res["pre_15m_dir"] != res["react_dir"]:
                    st["pre15_opp"] += 1

            if res["pre_1h_dir"] != "flat" and res["react_dir"] != "flat":
                st["pre1h_valid"] += 1
                if res["pre_1h_dir"] != res["react_dir"]:
                    st["pre1h_opp"] += 1

            for key, bucket in (("post_15m", "post15_list"), ("post_30m", "post30_list"), ("post_1h", "post1h_list")):
                if res[key] is not None:
                    st[bucket].append(abs(res[key]))

    # Upsert into Supabase
    for etype, st in type_stats.items():
        if st["total"] == 0:
            continue
        row = {
            "event_type":           etype,
            "total_events":         st["total"],
            "pre_15m_opposite_pct": round(st["pre15_opp"] / st["pre15_valid"] * 100, 1) if st["pre15_valid"] else None,
            "pre_1h_opposite_pct":  round(st["pre1h_opp"] / st["pre1h_valid"] * 100, 1) if st["pre1h_valid"] else None,
            "avg_post_15m_abs":     round(float(np.mean(st["post15_list"])), 4) if st["post15_list"] else None,
            "avg_post_30m_abs":     round(float(np.mean(st["post30_list"])), 4) if st["post30_list"] else None,
            "avg_post_1h_abs":      round(float(np.mean(st["post1h_list"])),  4) if st["post1h_list"] else None,
            "surprise_align_pct":   None,   # requires consensus forecasts (not available free)
            "last_updated":         datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("event_patterns").upsert(row, on_conflict="event_type").execute()
        log.info("  ✓ %-20s  n=%d  pre15_opp=%.0f%%", etype, st["total"],
                 row["pre_15m_opposite_pct"] or 0)


if __name__ == "__main__":
    main()
