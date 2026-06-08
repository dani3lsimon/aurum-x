# backend/engines/macro_bias.py
"""
Lightweight macro bias score (-100 bearish .. +100 bullish) derived from the
latest fundamental agent scores — used as a quick fundamentals summary input
to the technical fusion agent. No LLM call; pure aggregation of the agents
that most directly drive gold's macro backdrop.
"""
import logging
from services.supabase_service import get_latest_agent_scores

logger = logging.getLogger(__name__)

# Agents most directly relevant to gold's macro/fundamental backdrop
_CORE_AGENTS = ["macro_agent", "fed_agent", "yield_agent", "dollar_agent",
                "liquidity_agent", "sentiment_agent"]


async def get_macro_bias() -> float:
    """Average score (-100..+100) across the core fundamental agents.
    Returns 0.0 if no scores are available — never fabricates a value."""
    try:
        scores = await get_latest_agent_scores() or []
        core = [s for s in scores if s.get("agent_name") in _CORE_AGENTS and s.get("score") is not None]
        if not core:
            return 0.0
        avg = sum(float(s["score"]) for s in core) / len(core)
        return round(avg, 1)
    except Exception as e:
        logger.error(f"macro_bias error: {e}")
        return 0.0
