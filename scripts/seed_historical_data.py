"""
scripts/seed_historical_data.py
Seed AURUM-X Supabase tables with static reference data.
Run from repo root: python scripts/seed_historical_data.py
Market data tables (gold_prices, yield_data, etc.) are populated by live agents.
"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def upsert(table: str, rows: list[dict]):
    if not rows:
        return
    sb.table(table).upsert(rows).execute()
    print(f"  [ok] {table} — {len(rows)} rows")


def seed_historical_environments():
    rows = [
        {"period_start": "2020-03-01", "period_end": "2020-08-31", "label": "2020 COVID Shock",
         "regimes": ["crisis", "qe"], "gold_return_pct": 28.5, "avg_gold_price": 1750.0,
         "notes": "Gold surged from $1470 to $2067 as Fed balance sheet expanded aggressively."},
        {"period_start": "2021-01-01", "period_end": "2021-12-31", "label": "2021 Reflation Trade",
         "regimes": ["reflation", "recovery"], "gold_return_pct": -3.6, "avg_gold_price": 1800.0,
         "notes": "Gold underperformed as real yields rose and equities surged."},
        {"period_start": "2022-01-01", "period_end": "2022-12-31", "label": "2022 Fed Hiking Cycle",
         "regimes": ["tightening", "war"], "gold_return_pct": -0.3, "avg_gold_price": 1800.0,
         "notes": "Gold flat — Ukraine war provided floor, strong USD capped upside."},
        {"period_start": "2023-03-01", "period_end": "2023-05-31", "label": "2023 Banking Crisis",
         "regimes": ["stress", "pause"], "gold_return_pct": 9.1, "avg_gold_price": 1950.0,
         "notes": "Gold rallied $150 in 6 weeks on SVB/Credit Suisse stress."},
        {"period_start": "2024-01-01", "period_end": "2024-12-31", "label": "2024 Bull Run",
         "regimes": ["bull", "cb_buying"], "gold_return_pct": 27.2, "avg_gold_price": 2300.0,
         "notes": "Gold hit ATH driven by record central bank purchases and geopolitical tail risks."},
        {"period_start": "2025-01-01", "period_end": "2025-12-31", "label": "2025 ATH Extension",
         "regimes": ["bull", "tariff_risk"], "gold_return_pct": 26.0, "avg_gold_price": 2900.0,
         "notes": "Gold extended ATH above $3000 as tariff uncertainty drove renewed ETF inflows."},
    ]
    upsert("historical_environments", rows)


def seed_economic_releases():
    rows = [
        {"event": "CPI",           "country": "US", "release_date": "2026-06-11T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "PPI",           "country": "US", "release_date": "2026-06-12T12:30:00+00:00", "impact": "medium", "gold_sensitivity": "medium",   "direction_actual": "unknown", "source": "calendar"},
        {"event": "FOMC Decision", "country": "US", "release_date": "2026-06-18T18:00:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "GDP",           "country": "US", "release_date": "2026-06-26T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "high",     "direction_actual": "unknown", "source": "calendar"},
        {"event": "PCE",           "country": "US", "release_date": "2026-06-27T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "NFP",           "country": "US", "release_date": "2026-07-03T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "high",     "direction_actual": "unknown", "source": "calendar"},
        {"event": "CPI",           "country": "US", "release_date": "2026-07-15T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "FOMC Decision", "country": "US", "release_date": "2026-07-30T18:00:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "NFP",           "country": "US", "release_date": "2026-08-07T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "high",     "direction_actual": "unknown", "source": "calendar"},
        {"event": "CPI",           "country": "US", "release_date": "2026-08-12T12:30:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
        {"event": "FOMC Decision", "country": "US", "release_date": "2026-09-17T18:00:00+00:00", "impact": "high",   "gold_sensitivity": "critical", "direction_actual": "unknown", "source": "calendar"},
    ]
    upsert("economic_releases", rows)


if __name__ == "__main__":
    print("\n=== AURUM-X Historical Data Seed ===\n")
    seed_historical_environments()
    seed_economic_releases()
    print("\n=== Seed complete ===\n")
