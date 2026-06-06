# backend/agents/geopolitical_agent.py — HAIKU, 30-min skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector
from collectors.macro_collector import MacroCollector


class GeopoliticalAgent(BaseAgent):
    def __init__(self):
        super().__init__("geopolitical_agent", "Interprets geopolitical events for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()
        self.macro = MacroCollector()

    async def collect_data(self) -> dict:
        news = await self.collector.get_geopolitical_news()
        compressed = [item.get("headline", item.get("title", str(item)))[:120]
                      for item in (news or [])[:5]]

        # If no geo news, use real-yield and commodity macro context as proxy
        proxy_ctx = {}
        if not compressed:
            try:
                indicators = await self.macro.get_latest_indicators()
                for k in ["REAL_YIELD_10Y", "INFLATION_EXPECTATIONS_10Y", "FED_FUNDS"]:
                    v = indicators.get(k, {})
                    if isinstance(v, dict) and v.get("latest"):
                        proxy_ctx[k] = v["latest"].get("value")
            except Exception:
                pass

        return {"geo_news": compressed, "macro_proxy": proxy_ctx}

    def build_prompt(self, data: dict) -> str:
        geo_news = data.get("geo_news", [])
        proxy = data.get("macro_proxy", {})

        if geo_news:
            context = f"Geo events: {geo_news}"
        else:
            context = (
                f"No live geo headlines. Macro proxy: "
                f"Real Yield 10Y={proxy.get('REAL_YIELD_10Y')}%, "
                f"Inflation Expectations 10Y={proxy.get('INFLATION_EXPECTATIONS_10Y')}%, "
                f"Fed Funds={proxy.get('FED_FUNDS')}%. "
                "Assess baseline geopolitical safe-haven demand for gold given current rates environment."
            )

        return f"""{context}
Score gold: war/sanctions escalation, energy disruption, safe-haven demand.
Respond with JSON only. No preamble."""
