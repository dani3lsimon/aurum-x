# backend/agents/liquidity_agent.py — HAIKU, 2-hr skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.fmp_collector import FMPCollector
from collectors.macro_collector import MacroCollector


class LiquidityAgent(BaseAgent):
    def __init__(self):
        super().__init__("liquidity_agent", "Interprets global liquidity conditions",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.fmp  = FMPCollector()
        self.fred = MacroCollector()

    async def collect_data(self) -> dict:
        fed  = await self.fred.get_fed_data()
        compressed = {}
        for k in ["FED_FUNDS", "FED_BALANCE_SHEET", "M2"]:
            v = fed.get(k, {})
            compressed[k] = v.get("latest", {}).get("value") if isinstance(v, dict) else v
        return {"fed": compressed}

    def build_prompt(self, data: dict) -> str:
        return f"""Fed/liquidity: {data}
Score gold: balance sheet expansion/contraction, M2 growth, QT pace.
Expansion=bullish. QT=bearish.
Respond with JSON only. No preamble."""
