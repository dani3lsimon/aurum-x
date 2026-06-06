# backend/agents/news_agent.py — HAIKU, 30-min skip cache, max 5 headlines
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector
from collectors.macro_collector import MacroCollector


class NewsAgent(BaseAgent):
    def __init__(self):
        super().__init__("news_agent", "Interprets financial news for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()
        self.macro = MacroCollector()

    async def collect_data(self) -> dict:
        news = await self.collector.get_recent_news()
        compressed = []
        for item in (news or [])[:5]:
            h = item.get("headline") or item.get("title") or str(item)[:100]
            compressed.append(h[:120])

        # If no live news, enrich with FRED macro context as proxy signal
        macro_ctx = {}
        if not compressed:
            try:
                indicators = await self.macro.get_latest_indicators()
                for k in ["CPI", "CORE_PCE", "UNEMPLOYMENT", "FED_FUNDS"]:
                    v = indicators.get(k, {})
                    if isinstance(v, dict) and v.get("latest"):
                        macro_ctx[k] = v["latest"].get("value")
            except Exception:
                pass

        return {"headlines": compressed, "macro_fallback": macro_ctx}

    def build_prompt(self, data: dict) -> str:
        headlines = data.get("headlines", [])
        macro = data.get("macro_fallback", {})

        if headlines:
            context = f"Headlines: {headlines}"
        else:
            context = f"No live headlines. Macro context: CPI={macro.get('CPI')}, Core PCE={macro.get('CORE_PCE')}, Unemployment={macro.get('UNEMPLOYMENT')}, Fed Funds={macro.get('FED_FUNDS')}%"

        return f"""{context}
Net score gold: Fed implications, inflation signals, risk sentiment, dollar direction.
Respond with JSON only. No preamble."""
