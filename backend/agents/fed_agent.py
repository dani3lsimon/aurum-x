# backend/agents/fed_agent.py
# Default: Haiku. Sonnet injected by scheduler for daily 08:00 UTC deep run.
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.macro_collector import MacroCollector


class FedAgent(BaseAgent):
    def __init__(self, model=None, skip_ttl=CACHE_TTL_STANDARD):
        super().__init__(
            "fed_agent",
            "Interprets Federal Reserve communications",
            model=model or MODEL_HAIKU,
            skip_ttl=skip_ttl,
        )
        self.collector = MacroCollector()
        self.data_source = 'FRED'

    async def collect_data(self) -> dict:
        return await self.collector.get_fed_data()

    def build_prompt(self, data: dict) -> str:
        return f"""Fed data: {data}
Score gold: fed funds rate, QT pace, balance sheet, dovish/hawkish tone.
Rate cuts=bullish. Hikes=bearish. QE=bullish. QT=bearish.
Respond with JSON only. No preamble."""
