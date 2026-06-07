# backend/collectors/positioning_collector.py
"""
CFTC Public API collector for gold COT data.
NO API key required. NO FMP. NO hardcoded data.
Dataset: 72hh-3qpy (Disaggregated Futures Only Report) — publicreporting.cftc.gov
Gold contract code: 088691 (GOLD - COMMODITY EXCHANGE INC.)
Released every Friday ~3:30pm ET, covering prior Tuesday's positions.

Verified live field names on 2026-06-07 (subject to CFTC's own naming quirks):
  m_money_positions_long_all / m_money_positions_short_all / m_money_positions_spread
  prod_merc_positions_long / prod_merc_positions_short
  swap_positions_long_all / swap__positions_short_all  (note double underscore)
  other_rept_positions_long / other_rept_positions_short
  open_interest_all, report_date_as_yyyy_mm_dd
"""
import httpx
import logging
from datetime import datetime
from services.redis_service import cache_get, cache_set, cache_delete
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

CFTC_API_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
GOLD_CONTRACT_CODE = "088691"
CACHE_KEY = "cftc_gold_cot_analysis"


def _f(row: dict, *keys) -> float:
    """Try multiple possible field-name spellings (CFTC renames fields across years)."""
    for k in keys:
        if k in row and row[k] not in (None, ""):
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return 0.0


class PositioningCollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _fetch_cftc(self, limit: int = 8) -> list:
        params = {
            "$where": f"cftc_contract_market_code='{GOLD_CONTRACT_CODE}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": limit,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(CFTC_API_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_latest(self, force: bool = False) -> dict:
        """Fetch + analyse last 8 weeks of gold managed-money COT positioning. Cached 6h."""
        if not force:
            cached = await cache_get(CACHE_KEY)
            if cached:
                return cached

        try:
            raw = await self._fetch_cftc(limit=8)
        except Exception as e:
            logger.error(f"CFTC API request failed: {e}")
            return {"error": f"CFTC API request failed: {e}", "source": "cftc_public_api"}

        if not raw:
            return {"error": "CFTC API returned no records for gold (088691)", "source": "cftc_public_api"}

        weeks = []
        for row in raw:
            try:
                report_date   = row.get("report_date_as_yyyy_mm_dd", "")[:10]
                open_interest = _f(row, "open_interest_all")

                mm_long   = _f(row, "m_money_positions_long_all")
                mm_short  = _f(row, "m_money_positions_short_all")
                mm_spread = _f(row, "m_money_positions_spread", "m_money_positions_spread_all")

                comm_long  = _f(row, "prod_merc_positions_long", "prod_merc_positions_long_all")
                comm_short = _f(row, "prod_merc_positions_short", "prod_merc_positions_short_all")

                swap_long  = _f(row, "swap_positions_long_all")
                swap_short = _f(row, "swap__positions_short_all", "swap_positions_short_all")

                other_long  = _f(row, "other_rept_positions_long", "other_rept_positions_long_all")
                other_short = _f(row, "other_rept_positions_short", "other_rept_positions_short_all")

                mm_net    = mm_long - mm_short
                comm_net  = comm_long - comm_short
                other_net = other_long - other_short
                mm_net_pct_oi = (mm_net / open_interest * 100) if open_interest else 0.0

                weeks.append({
                    "date":            report_date,
                    "open_interest":   open_interest,
                    "mm_long":         mm_long,
                    "mm_short":        mm_short,
                    "mm_spread":       mm_spread,
                    "mm_net":          mm_net,
                    "mm_net_pct_oi":   round(mm_net_pct_oi, 2),
                    "comm_long":       comm_long,
                    "comm_short":      comm_short,
                    "comm_net":        comm_net,
                    "swap_long":       swap_long,
                    "swap_short":      swap_short,
                    "other_long":      other_long,
                    "other_short":     other_short,
                    "other_net":       other_net,
                })
            except Exception as e:
                logger.warning(f"Skipping malformed CFTC row: {e}")
                continue

        if not weeks:
            return {"error": "Failed to parse CFTC rows — field schema may have changed", "source": "cftc_public_api"}

        weeks_asc = sorted(weeks, key=lambda w: w["date"])
        mm_series = [w["mm_net"] for w in weeks_asc]

        trend = "up" if mm_series[-1] > mm_series[0] else "down"
        net_change_8w = mm_series[-1] - mm_series[0]

        # Consecutive streak (week-over-week direction) ending at latest week
        streak = 1
        streak_direction = None
        for i in range(len(mm_series) - 1, 0, -1):
            diff = mm_series[i] - mm_series[i - 1]
            direction = "up" if diff > 0 else "down"
            if streak_direction is None:
                streak_direction = direction
            if direction == streak_direction:
                streak += 1
            else:
                break

        max_net, min_net = max(mm_series), min(mm_series)
        range_net = max_net - min_net
        latest_net = mm_series[-1]
        pct_of_range = ((latest_net - min_net) / range_net * 100) if range_net else 50.0
        is_extreme_long  = pct_of_range > 80
        is_extreme_short = pct_of_range < 20

        result = {
            "source":           "cftc_public_api",
            "dataset":          "72hh-3qpy (Disaggregated Futures Only)",
            "commodity":        "Gold (COMEX 100 Troy Oz)",
            "contract_code":    GOLD_CONTRACT_CODE,
            "primary_signal":   "managed_money",
            "weeks_analysed":   len(weeks_asc),
            "latest":           weeks_asc[-1],
            "previous_week":    weeks_asc[-2] if len(weeks_asc) > 1 else None,
            "all_weeks":        weeks_asc,
            "trend_8w":         trend,
            "net_change_8w":    round(net_change_8w, 0),
            "current_streak":   streak,
            "streak_direction": streak_direction,
            "pct_of_8w_range":  round(pct_of_range, 1),
            "is_extreme_long":  is_extreme_long,
            "is_extreme_short": is_extreme_short,
            "fetched_at":       datetime.utcnow().isoformat(),
        }

        await cache_set(CACHE_KEY, result, ttl_seconds=21600)
        logger.info(
            f"CFTC COT (real data): {len(weeks_asc)} weeks | "
            f"latest mm_net={latest_net:,.0f} | trend={trend} | "
            f"streak={streak}w {streak_direction} | "
            f"extreme_long={is_extreme_long} extreme_short={is_extreme_short}"
        )
        return result

    async def update_from_cftc(self) -> dict:
        """Force refresh — bypasses cache and refetches from CFTC directly."""
        await cache_delete(CACHE_KEY)
        return await self.get_latest(force=True)
