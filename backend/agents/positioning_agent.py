# backend/agents/positioning_agent.py — HAIKU, 2-hr skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.positioning_collector import PositioningCollector
from collectors.macro_collector import MacroCollector


class PositioningAgent(BaseAgent):
    def __init__(self):
        super().__init__("positioning_agent", "Interprets CFTC COT and ETF flows",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.collector = PositioningCollector()
        self.macro = MacroCollector()

    async def collect_data(self) -> dict:
        data = await self.collector.get_latest()

        # If no COT data, supply price-trend proxy from macro indicators
        if data.get("status") == "no_data" or not data.get("latest") and not data.get("latest_fmp"):
            try:
                indicators = await self.macro.get_latest_indicators()
                proxy = {}
                for k in ["FED_FUNDS", "REAL_YIELD_10Y", "INFLATION_EXPECTATIONS_10Y"]:
                    v = indicators.get(k, {})
                    if isinstance(v, dict) and v.get("latest"):
                        proxy[k] = v["latest"].get("value")
                data["macro_proxy"] = proxy
                data["note"] = "No CFTC data available. Using macro proxy for positioning inference."
            except Exception:
                pass

        return data

    def build_prompt(self, data: dict) -> str:
        note = data.get("note", "")
        proxy = data.get("macro_proxy", {})

        if note:
            context = (
                f"No direct CFTC COT data available. "
                f"Macro proxy: Real Yield 10Y={proxy.get('REAL_YIELD_10Y')}%, "
                f"Inflation Exp 10Y={proxy.get('INFLATION_EXPECTATIONS_10Y')}%, "
                f"Fed Funds={proxy.get('FED_FUNDS')}%. "
                "Infer likely managed-money gold positioning from macro backdrop."
            )
        else:
            context = f"COT data: {data}"

        return f"""{context}
Score gold: managed money net position, crowding risk, open interest trend.
Extreme long=reversal risk. Commercial net=smart money.
Respond with JSON only. No preamble."""
