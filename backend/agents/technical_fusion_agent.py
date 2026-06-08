# backend/agents/technical_fusion_agent.py — SONNET, fuses deterministic SMC
# price-action structure with fundamental agent scores into a single concrete
# trade thesis (direction, entry zone, invalidation, targets, conviction).
#
# Deliberately NOT a BaseAgent subclass: BaseAgent.run() forces the standard
# score/confidence/rationale schema (AGENT_SYSTEM_PROMPT) and persists into
# agent_scores — this agent returns a bespoke trade-thesis schema instead, so
# it follows the same direct-Anthropic-call pattern as scenario_engine.py.
import anthropic
import json
import asyncio
import logging
from config import get_settings, MODEL_SONNET, MAX_TOKENS_SONNET, estimate_cost
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()
client   = anthropic.Anthropic()

CACHE_KEY = "technical_fusion_signal"
CACHE_TTL = 300  # 5 min — matches multi-tf engine cycle


class TechnicalFusionAgent:
    """Senior-trader fusion of deterministic SMC structure with fundamentals.
    Trusts the SMC engine's price levels verbatim — never recalculates them."""

    agent_name = "technical_fusion"
    model      = MODEL_SONNET
    cache_ttl  = CACHE_TTL

    async def collect_data(self) -> dict:
        from engines.patterns_engine import analyze_all
        from engines.macro_bias import get_macro_bias
        from services.supabase_service import get_latest_agent_scores, get_latest_forecast

        smc      = await analyze_all()
        agents   = await get_latest_agent_scores()
        forecast = await get_latest_forecast()
        mbs      = await get_macro_bias()
        fundamentals = {s.get("agent_name"): {"score": s.get("score"), "bias": s.get("raw_data", {}).get("directional_bias")}
                        for s in (agents or [])}
        return {"smc": smc, "fundamentals": fundamentals, "mbs": mbs,
                "regime": forecast.get("macro_regime") if forecast else "unknown"}

    def build_prompt(self, data: dict) -> str:
        return f"""You are a senior gold (XAUUSD) trader fusing Smart Money Concepts price-action with macro fundamentals.

The SMC data below is from a deterministic engine — TRUST the patterns and price levels, do not recalculate.

SMC PATTERNS (15m/1h/4h) — net_confluence -5 bearish .. +5 bullish:
{json.dumps(data['smc'], indent=2)}

FUNDAMENTAL AGENT SCORES (-100 bearish .. +100 bullish):
{json.dumps(data['fundamentals'], indent=2)}

MACRO BIAS SCORE: {data['mbs']}   REGIME: {data['regime']}

Produce ONLY this JSON (no markdown):
{{
  "direction": "LONG"|"SHORT"|"NEUTRAL",
  "probability": <int 0-100, chance first target hit within 4h>,
  "entry_zone": "<price range from an SMC level>",
  "entry_rationale": "<which SMC structure supports entry>",
  "invalidation": "<price + which structure invalidates it>",
  "first_target": "<price>",
  "second_target": "<price or null>",
  "target_rationale": "<where targets come from>",
  "setup_quality": "HIGH_CONVICTION"|"SCALP"|"WEAK"|"NO_TRADE",
  "timeframe_alignment": "<do 15m/1h/4h agree?>",
  "reasoning": "<2-3 sentences fusing SMC structure with fundamentals>",
  "risk_note": "<what abandons this view early>"
}}

Rules: every price level must come from the SMC data. If SMC and fundamentals conflict, say so and lower probability. If net_confluence is between -1 and +1, default to NO_TRADE. Score your own confidence honestly."""

    async def run(self) -> dict:
        cached = await cache_get(CACHE_KEY)
        if cached:
            return cached

        try:
            data   = await self.collect_data()
            prompt = self.build_prompt(data)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS_SONNET,
                    system="You are a precise, honest trading analyst. Respond with raw JSON only — no markdown, no preamble.",
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            in_tok  = response.usage.input_tokens
            out_tok = response.usage.output_tokens
            cost    = estimate_cost(self.model, in_tok, out_tok)

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            result = json.loads(raw)
            result["generated_at"] = data["smc"].get("net_confluence") and __import__("datetime").datetime.utcnow().isoformat()

            logger.info(
                f"[technical_fusion] {result.get('direction')} | "
                f"quality={result.get('setup_quality')} | prob={result.get('probability')}% | "
                f"tokens in={in_tok} out={out_tok} estimated_cost=${cost:.5f}"
            )

            await cache_set(CACHE_KEY, result, ttl_seconds=self.cache_ttl)
            return result

        except Exception as e:
            logger.error(f"[technical_fusion] error: {e}")
            return {"direction": "NEUTRAL", "probability": 0, "setup_quality": "NO_TRADE",
                    "reasoning": f"Fusion agent error: {e}", "error": str(e)}
