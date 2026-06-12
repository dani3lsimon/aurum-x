# backend/agents/base_agent.py
from abc import ABC, abstractmethod
import httpx
import json
import logging
from datetime import datetime
from config import (
    get_settings, estimate_deepseek_cost,
    MAX_TOKENS_HAIKU, CACHE_TTL_STANDARD,
    MODEL_HAIKU, MODEL_SONNET, MAX_TOKENS_SONNET,
    DEEPSEEK_BASE_URL, DEEPSEEK_MODEL_LIGHT, DEEPSEEK_MODEL_HEAVY,
)
from services.supabase_service import insert_agent_score
from services.websocket_manager import ws_manager
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()

AGENT_SYSTEM_PROMPT = """You are an institutional macro analyst specialising in XAUUSD (Gold).
You MUST respond with a valid JSON object containing ALL of these exact fields — no exceptions:
{
  "score": float,
  "confidence": float,
  "rationale": string,
  "regime": string,
  "key_factors": [list of strings],
  "signal_strength": string,
  "directional_bias": string,
  "data_quality": string,
  "notable_risk": string
}

Field rules:
- score: -100 to +100. Positive = bullish gold. Negative = bearish. 0 = neutral.
- confidence: 0-100. How certain you are given the data quality and clarity of signal.
- rationale: 2-3 precise sentences. MUST cite specific numbers from the data provided (e.g. "CPI at 3.2% YoY, above the 3.0% forecast"). Never write generic statements.
- regime: The macro regime you detect. One of: inflation_shock | disinflation | recession_risk | growth_expansion | liquidity_expansion | liquidity_contraction | rate_hike_cycle | rate_cut_cycle | geopolitical_crisis | risk_off | unknown
- key_factors: List of 3-5 strings. Each MUST cite a specific data value and its directional implication for gold. Example: "Real yield 2.11% — elevated but stable, mild headwind for gold"
- signal_strength: One of: strong | moderate | weak | neutral
- directional_bias: One of: bullish | bearish | neutral
- data_quality: One of: high | medium | low. Use 'low' if data is missing, stale, or estimated. Use 'high' only if you received complete, current, real data.
- notable_risk: One sentence on the primary risk to your view. What could make this score wrong? If no notable risk, write "none identified".

Score calibration:
+80 to +100 = maximally bullish (hyperinflation + rate cuts + dollar collapse + VIX spike simultaneously)
+40 to +79  = moderately to strongly bullish
+10 to +39  = mildly bullish
-10 to +10  = neutral
-11 to -39  = mildly bearish
-40 to -79  = moderately to strongly bearish
-80 to -100 = maximally bearish

Return only the JSON object. No markdown. No preamble. No explanation outside the JSON."""


class BaseAgent(ABC):
    """
    All agents default to Haiku (cheap).
    MacroAgent/FedAgent can override model=MODEL_SONNET for the daily deep run.
    Smart skip: if prompt hash matches Redis key, skip Claude entirely.
    DeepSeek fires automatically if Anthropic fails.
    """

    def __init__(self, name: str, description: str,
                 model: str = MODEL_HAIKU,
                 skip_ttl: int = CACHE_TTL_STANDARD,
                 max_tokens: int = None):
        self.name        = name
        self.description = description
        self.model       = model
        self.skip_ttl    = skip_ttl   # how long to cache prompt hash (= cycle time)
        self.max_tokens  = max_tokens or (MAX_TOKENS_SONNET if "sonnet" in model else MAX_TOKENS_HAIKU)
        self.ds_model    = DEEPSEEK_MODEL_HEAVY if "sonnet" in model else DEEPSEEK_MODEL_LIGHT

        self.last_score:      float = 0.0
        self.last_rationale:  str   = ""
        self.last_confidence: float = 50.0
        self.data_source:     str   = "unknown"

    @abstractmethod
    async def collect_data(self) -> dict:
        pass

    @abstractmethod
    def build_prompt(self, data: dict) -> str:
        pass

    # ── DeepSeek fallback ──────────────────────────────────────────────────

    async def _call_deepseek(self, prompt: str) -> tuple[dict, int, int]:
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")
        payload = {
            "model": self.ds_model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type":  "application/json",
        }
        async with httpx.AsyncClient(timeout=90) as http:
            resp = await http.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                                   json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        msg = data["choices"][0]["message"]
        # deepseek-reasoner puts final answer in content; chain-of-thought in reasoning_content
        raw = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]
        usage = data.get("usage", {})
        return json.loads(raw), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    # ── Prompt stripper (strips markdown fences) ───────────────────────────

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return text.strip()

    # ── Main run ───────────────────────────────────────────────────────────

    async def run(self) -> dict:
        try:
            data   = await self.collect_data()
            prompt = self.build_prompt(data)

            # ── Smart skip: prompt-hash cache ──────────────────────────
            prompt_hash = hash(prompt[:300])
            skip_key    = f"skip:{self.name}:{prompt_hash}"
            last_score_key = f"last_score:{self.name}"

            if await cache_get(skip_key):
                cached_score = await cache_get(last_score_key)
                if cached_score:
                    logger.info(f"[{self.name}] PROMPT UNCHANGED — skip DeepSeek ($0.00)")
                    return cached_score

            # ── Call DeepSeek Reasoner ─────────────────────────────────
            result   = None
            in_tok   = out_tok = 0
            provider = "deepseek_reasoner"

            try:
                result, in_tok, out_tok = await self._call_deepseek(prompt)
                cost = estimate_deepseek_cost(self.ds_model, in_tok, out_tok)
                logger.info(
                    f"[{self.name}] provider=deepseek_reasoner "
                    f"model={self.ds_model} "
                    f"tokens in={in_tok} out={out_tok} "
                    f"estimated_cost=${cost:.5f}"
                )
            except Exception as ds_err:
                logger.error(f"[{self.name}] DeepSeek failed: {ds_err}")
                return {"agent_name": self.name, "score": 0, "confidence": 0,
                        "rationale": f"DeepSeek error: {ds_err}"}

            # ── Build score record ─────────────────────────────────────
            self.last_score      = float(result.get("score", 0))
            self.last_confidence = float(result.get("confidence", 50))
            self.last_rationale  = result.get("rationale", "")

            score_record = {
                "agent_name":  self.name,
                "score":       self.last_score,
                "confidence":  self.last_confidence,
                "rationale":   self.last_rationale,
                "raw_data":    {**result, "provider": provider,
                                "tokens_in": in_tok, "tokens_out": out_tok},
                "regime":      result.get("regime"),
                "data_source": getattr(self, "data_source", "unknown"),
                "timestamp":   datetime.utcnow().isoformat(),
            }

            # ── Persist + broadcast ────────────────────────────────────
            await insert_agent_score(score_record)
            await ws_manager.send_agent_update(
                self.name, self.last_score, self.last_rationale
            )

            # ── Cache prompt hash (smart skip) + last score ────────────
            await cache_set(skip_key, True, ttl_seconds=self.skip_ttl)
            await cache_set(last_score_key, score_record, ttl_seconds=self.skip_ttl * 2)

            logger.info(
                f"[{self.name}] Score: {self.last_score:.1f} | "
                f"Conf: {self.last_confidence:.0f}% | "
                f"Bias: {result.get('directional_bias', '?')} | "
                f"Strength: {result.get('signal_strength', '?')} | "
                f"Quality: {result.get('data_quality', '?')}"
            )
            return score_record

        except json.JSONDecodeError as e:
            raw = locals().get("raw_text", "")
            logger.error(f"[{self.name}] JSON parse error: {e} — raw: {raw[:200]}")
            return {"agent_name": self.name, "score": 0, "confidence": 0,
                    "rationale": f"Parse error: {e}"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error: {e}")
            return {"agent_name": self.name, "score": 0, "confidence": 0,
                    "rationale": f"Error: {e}"}
