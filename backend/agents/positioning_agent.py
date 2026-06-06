# backend/agents/positioning_agent.py — HAIKU, 2-hr skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.positioning_collector import PositioningCollector


class PositioningAgent(BaseAgent):
    def __init__(self):
        super().__init__("positioning_agent", "Interprets CFTC COT and ETF flows",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.collector = PositioningCollector()

    async def collect_data(self) -> dict:
        return await self.collector.get_latest()

    def build_prompt(self, data: dict) -> str:
        return f"""COT data: {data}
Score gold: managed money net position, crowding risk, open interest trend.
Extreme long=reversal risk. Commercial net=smart money.
Respond with JSON only. No preamble."""
