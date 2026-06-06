# backend/agents/geopolitical_agent.py — HAIKU, 30-min skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector


class GeopoliticalAgent(BaseAgent):
    def __init__(self):
        super().__init__("geopolitical_agent", "Interprets geopolitical events for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()

    async def collect_data(self) -> dict:
        news = await self.collector.get_geopolitical_news()
        compressed = [item.get("headline", item.get("title", str(item)))[:120]
                      for item in (news or [])[:5]]
        return {"geo_news": compressed}

    def build_prompt(self, data: dict) -> str:
        return f"""Geo events: {data.get('geo_news', [])}
Score gold: war/sanctions escalation, energy disruption, safe-haven demand.
Respond with JSON only. No preamble."""
