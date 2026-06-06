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
