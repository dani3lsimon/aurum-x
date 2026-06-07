# backend/collectors/macro_collector.py
# FRED API — actual release values for macro indicators
import httpx
from config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "CPI":                       "CPIAUCSL",
    "CORE_CPI":                  "CPILFESL",
    "PPI":                       "PPIACO",
    "PCE":                       "PCE",
    "CORE_PCE":                  "PCEPILFE",
    "NFP":                       "PAYEMS",
    "UNEMPLOYMENT":              "UNRATE",
    "GDP":                       "GDP",
    "RETAIL_SALES":              "RSAFS",
    "JOLTS":                     "JTSJOL",
    "FED_FUNDS":                 "FEDFUNDS",
    "FED_BALANCE_SHEET":         "WALCL",
    "M2":                        "M2SL",
    "SOFR":                      "SOFR",
    "INFLATION_EXPECTATIONS_5Y": "T5YIE",
    "INFLATION_EXPECTATIONS_10Y":"T10YIE",
    "REAL_YIELD_10Y":            "DFII10",
    "BREAKEVEN_10Y":             "T10YIE",
}


class MacroCollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _fetch_fred(self, series_id: str, limit: int = 3) -> dict:
        params = {
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])
            return {
                "series": series_id,
                "latest": observations[0] if observations else None,
                "previous": observations[1] if len(observations) > 1 else None,
            }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _fetch_fred_observations(self, series_id: str, limit: int = 6) -> list:
        """
        Raw observations array (newest first), for momentum/trend calcs that need
        more than the latest+previous pair _fetch_fred() returns. FRED daily FX/DXY
        series carry '.' for non-trading days — caller must filter those out.
        """
        params = {
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            return resp.json().get("observations", [])

    async def get_latest_indicators(self) -> dict:
        results = {}
        for name, series_id in FRED_SERIES.items():
            try:
                results[name] = await self._fetch_fred(series_id)
            except Exception as e:
                logger.warning(f"FRED fetch failed [{name}]: {e}")
                results[name] = {"error": str(e)}
        return results

    async def get_fed_data(self) -> dict:
        fed_series = {
            "FED_FUNDS":         "FEDFUNDS",
            "FED_BALANCE_SHEET": "WALCL",
            "M2":                "M2SL",
            "SOFR":              "SOFR",
            "INFLATION_EXP_5Y":  "T5YIE",
            "REAL_YIELD_10Y":    "DFII10",
        }
        results = {}
        for name, series_id in fed_series.items():
            try:
                results[name] = await self._fetch_fred(series_id)
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    async def get_yield_series(self) -> dict:
        """Real yields and breakevens from FRED."""
        yield_series = {
            "REAL_YIELD_5Y":   "DFII5",
            "REAL_YIELD_10Y":  "DFII10",
            "REAL_YIELD_30Y":  "DFII30",
            "BREAKEVEN_5Y":    "T5YIE",
            "BREAKEVEN_10Y":   "T10YIE",
        }
        results = {}
        for name, series_id in yield_series.items():
            try:
                results[name] = await self._fetch_fred(series_id)
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    async def get_dollar_data(self) -> dict:
        """
        FRED-based dollar-strength data — replaces FMP forex, which returns null
        on the current plan tier. DTWEXBGS (Trade Weighted Dollar Index, Broad) is
        the free, no-paywall DXY proxy; the FX series below give safe-haven context
        (JPY/CHF strength vs USD = risk-off signal relevant to gold).

        Series meaning (so callers don't need to guess direction):
          DTWEXBGS / DTWEXM = broad / major trade-weighted USD indices (higher = stronger USD)
          DEXUSEU = USD per 1 EUR  (= EURUSD spot)
          DEXJPUS = JPY per 1 USD  (= USDJPY spot)
          DEXUSUK = USD per 1 GBP  (= GBPUSD spot)
          DEXSZUS = CHF per 1 USD  (= USDCHF spot)
          DEXCHUS = CNH per 1 USD  (= USDCNH spot)

        Honest no-data: any series FRED can't serve comes back as {"error": ...} —
        no fabricated values, no silent fallback to stale numbers.
        """
        dollar_series = {
            "DXY_BROAD": "DTWEXBGS",
            "DXY_MAJOR": "DTWEXM",
            "EURUSD":    "DEXUSEU",
            "USDJPY":    "DEXJPUS",
            "GBPUSD":    "DEXUSUK",
            "USDCHF":    "DEXSZUS",
            "USDCNH":    "DEXCHUS",
        }
        results = {}
        for name, series_id in dollar_series.items():
            try:
                results[name] = await self._fetch_fred(series_id, limit=2)
            except Exception as e:
                logger.warning(f"FRED dollar fetch failed [{name}]: {e}")
                results[name] = {"error": str(e)}

        # Momentum: compare latest vs ~5 trading days back on the broad DXY proxy.
        # FRED daily FX series mark non-trading days with '.', so pull extra
        # observations and filter to real numeric values before comparing.
        try:
            obs = await self._fetch_fred_observations("DTWEXBGS", limit=8)
            valid = [o for o in obs if o.get("value") not in (None, ".", "")]
            if len(valid) >= 2:
                latest_val  = float(valid[0]["value"])
                earlier_val = float(valid[min(4, len(valid) - 1)]["value"])
                if earlier_val:
                    momentum = ((latest_val - earlier_val) / earlier_val) * 100
                    results["DXY_MOMENTUM_PCT"]   = round(momentum, 4)
                    results["DXY_DIRECTION"]      = "strengthening" if latest_val > earlier_val else "weakening"
                    results["DXY_LATEST_DATE"]    = valid[0].get("date")
                    results["DXY_COMPARE_DATE"]   = valid[min(4, len(valid) - 1)].get("date")
        except Exception as e:
            logger.warning(f"FRED DXY momentum calc failed: {e}")
            results["DXY_MOMENTUM_ERROR"] = str(e)

        return results
