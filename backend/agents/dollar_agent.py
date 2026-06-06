# backend/agents/dollar_agent.py — HAIKU, 2-hr skip cache, 3 pairs only
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.fmp_collector import FMPCollector


class DollarAgent(BaseAgent):
    def __init__(self):
        super().__init__("dollar_agent", "Interprets currency flows for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.fmp = FMPCollector()

    async def collect_data(self) -> dict:
        fx = await self.fmp.get_forex_rates()
        # Compress: only the 3 key pairs
        return {
            "EURUSD": fx.get("EURUSD"),
            "USDJPY": fx.get("USDJPY"),
            "USDCHF": fx.get("USDCHF"),
            "DXY_proxy": "derived from EURUSD/USDJPY",
        }

    def build_prompt(self, data: dict) -> str:
        return f"""FX: {data}
Score gold: DXY direction (up=bearish gold), JPY/CHF safe-haven signal.
Respond with JSON only. No preamble."""
