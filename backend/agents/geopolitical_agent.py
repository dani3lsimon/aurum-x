# backend/agents/geopolitical_agent.py — HAIKU, 30-min skip cache
# Source switched from FMP (tier-locked, returns null) to free RSS feeds — see
# collectors/news_collector.py (BBC World/NYT World + gold-wire geo-keyword filter).
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector


class GeopoliticalAgent(BaseAgent):
    def __init__(self):
        super().__init__("geopolitical_agent", "Interprets geopolitical events for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()
        self.data_source = 'RSS'

    async def collect_data(self) -> dict:
        news = await self.collector.get_geopolitical_news()
        compressed = []
        for item in (news or [])[:8]:
            title = (item.get("title") or item.get("headline") or str(item))[:140]
            compressed.append({"title": title, "source": item.get("tag", "general")})
        return {"geo_news": compressed, "source": "RSS — BBC World/NYT World + gold-wire geo-keyword filter"}

    def build_prompt(self, data: dict) -> str:
        geo_news = data.get("geo_news", [])
        if not geo_news:
            return """NO GEOPOLITICAL NEWS DATA AVAILABLE — all RSS feeds and the Finnhub fallback returned zero geo-relevant headlines.
Respond with JSON only: score=0, confidence=0, rationale="No data available — geo news feeds unreachable or no geo-relevant items found", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

        lines = "\n".join(f"- [{e['source']}] {e['title']}" for e in geo_news)
        return f"""Recent geopolitical events (source: {data.get('source')}, real published articles — no fabrication):

{lines}

Score gold impact: war/sanctions escalation, energy supply disruption, safe-haven demand, risk-off flows.
Cite at least one specific event by its content in your rationale and key_factors — no generic statements.
Respond with JSON only. No preamble."""
