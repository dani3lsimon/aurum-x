# backend/agents/regime_agent.py — HAIKU, 30-min skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_REGIME
from services.supabase_service import get_latest_agent_scores, insert_regime
from services.websocket_manager import ws_manager

VALID_REGIMES = [
    "inflation_shock", "disinflation", "recession_risk", "growth_expansion",
    "liquidity_expansion", "liquidity_contraction", "rate_hike_cycle",
    "rate_cut_cycle", "geopolitical_crisis", "risk_off",
]


class RegimeAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            "regime_agent",
            "Determines current macro regime",
            model=MODEL_HAIKU,
            skip_ttl=CACHE_TTL_REGIME,
        )
        self.data_source = 'Internal'

    async def collect_data(self) -> dict:
        scores = await get_latest_agent_scores()
        return {"agent_scores": scores, "valid_regimes": VALID_REGIMES}

    def build_prompt(self, data: dict) -> str:
        return f"""Agent scores: {data.get('agent_scores', [])}
Valid regimes: {data.get('valid_regimes', [])}
Classify primary macro regime. Set regime field to one valid string.
Respond with JSON only. No preamble."""

    async def run(self) -> dict:
        result = await super().run()
        if result.get("regime"):
            await insert_regime({
                "primary_regime":    result["regime"],
                "regime_confidence": result.get("confidence", 50),
            })
            await ws_manager.send_regime_change(
                result["regime"], "unknown", result.get("confidence", 50)
            )
        return result
