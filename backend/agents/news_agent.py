# backend/agents/news_agent.py — HAIKU, 30-min skip cache, max 5 headlines
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector


class NewsAgent(BaseAgent):
    def __init__(self):
        super().__init__("news_agent", "Interprets financial news for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()

    async def collect_data(self) -> dict:
        news = await self.collector.get_recent_news()
        compressed = []
        for item in (news or [])[:5]:
            h = item.get("headline") or item.get("title") or str(item)[:100]
            compressed.append(h[:120])
        return {"headlines": compressed}

    def build_prompt(self, data: dict) -> str:
        headlines = data.get("headlines", [])
        if not headlines:
            return """NO NEWS DATA AVAILABLE — the news feed returned zero headlines.
Respond with JSON only: score=0, confidence=0, rationale="No data available — news feed not connected", regime="UNKNOWN", key_factors=["no data source"].
No preamble."""
        return f"""Headlines: {headlines}
Net score gold: Fed implications, inflation signals, risk sentiment, dollar direction.
Respond with JSON only. No preamble."""
