# backend/agents/macro_agent.py
# Default: Haiku. Sonnet injected by scheduler for daily 08:00 UTC deep run.
from agents.base_agent import BaseAgent
from config import CACHE_TTL_STANDARD
from collectors.macro_collector import MacroCollector
from collectors.fmp_collector import FMPCollector


class MacroAgent(BaseAgent):
    def __init__(self, model=None, skip_ttl=CACHE_TTL_STANDARD):
        from config import MODEL_HAIKU
        super().__init__(
            "macro_agent",
            "Interprets economic releases for gold impact",
            model=model or MODEL_HAIKU,
            skip_ttl=skip_ttl,
        )
        self.fred = MacroCollector()
        self.fmp  = FMPCollector()

    async def collect_data(self) -> dict:
        fred_data = await self.fred.get_latest_indicators()
        fmp_macro = await self.fmp.get_macro_indicators()
        # Compress: 3 most recent data points per FRED indicator only
        compressed = {}
        for k, v in fred_data.items():
            if isinstance(v, dict) and "latest" in v:
                compressed[k] = {
                    "latest":   v.get("latest"),
                    "previous": v.get("previous"),
                }
        return {"fred": compressed, "fmp": fmp_macro}

    def build_prompt(self, data: dict) -> str:
        return f"""FRED: {data.get('fred', {})}
FMP: {data.get('fmp', {})}
Score gold: CPI/PPI trend, NFP, GDP, real yield shift, Fed path.
Respond with JSON only. No preamble."""
