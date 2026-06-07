# backend/agents/yield_agent.py — HAIKU, 2-hr skip cache, compressed yields only
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.fmp_collector import FMPCollector
from collectors.macro_collector import MacroCollector


class YieldAgent(BaseAgent):
    def __init__(self):
        super().__init__("yield_agent", "Interprets bond markets for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.fmp  = FMPCollector()
        self.fred = MacroCollector()
        self.data_source = 'FMP+FRED'

    async def collect_data(self) -> dict:
        yields = await self.fmp.get_treasury_yields()
        real   = await self.fred.get_yield_series()
        # Compress: only the key numbers
        return {
            "US2Y":        yields.get("US2Y"),
            "US10Y":       yields.get("US10Y"),
            "US30Y":       yields.get("US30Y"),
            "CURVE_2S10S": yields.get("CURVE_2S10S"),
            "CURVE_5S30S": yields.get("CURVE_5S30S"),
            "REAL_10Y":    real.get("REAL_YIELD_10Y", {}).get("latest", {}).get("value"),
            "BREAKEVEN_10Y": real.get("BREAKEVEN_10Y", {}).get("latest", {}).get("value"),
        }

    def build_prompt(self, data: dict) -> str:
        return f"""Yields: {data}
Score gold: real yield direction (key driver), curve inversion, breakeven trend.
Respond with JSON only. No preamble."""
