# backend/agents/news_agent.py — HAIKU, 30-min skip cache, max 8 headlines
# Source switched from FMP (tier-locked, returns null) to free RSS feeds — see
# collectors/news_collector.py (FXStreet/Mining.com/Investing.com/MarketWatch/Yahoo).
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.news_collector import NewsCollector


class NewsAgent(BaseAgent):
    def __init__(self):
        super().__init__("news_agent", "Interprets financial news for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_FAST)
        self.collector = NewsCollector()
        self.data_source = 'RSS'

    async def collect_data(self) -> dict:
        news = await self.collector.get_recent_news()
        compressed = []
        for item in (news or [])[:8]:
            title = (item.get("title") or item.get("headline") or str(item)[:100])[:140]
            compressed.append({"title": title, "source": item.get("tag", "general")})
        return {"headlines": compressed, "source": "RSS — FXStreet/Mining.com/Investing.com/MarketWatch/Yahoo Finance"}

    def build_prompt(self, data: dict) -> str:
        headlines = data.get("headlines", [])
        if not headlines:
            return """NO NEWS DATA AVAILABLE — all RSS feeds and the Finnhub fallback returned zero headlines.
Respond with JSON only: score=0, confidence=0, rationale="No data available — news feeds unreachable", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

        lines = "\n".join(f"- [{h['source']}] {h['title']}" for h in headlines)
        return f"""Recent gold/macro-relevant headlines (source: {data.get('source')}, real published articles — no fabrication):

{lines}

Score gold impact: Fed/rate implications, inflation signals, risk sentiment, dollar direction, safe-haven flows.
Cite at least one specific headline by its content in your rationale and key_factors — no generic statements.
Respond with JSON only. No preamble."""
