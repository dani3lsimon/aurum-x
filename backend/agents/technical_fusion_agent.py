# backend/agents/technical_fusion_agent.py — fuses deterministic SMC
# price-action structure with fundamental agent scores into a single concrete
# trade thesis (direction, entry zone, invalidation, targets, conviction).
#
# Deliberately NOT a BaseAgent subclass: BaseAgent.run() forces the standard
# score/confidence/rationale schema (AGENT_SYSTEM_PROMPT) and persists into
# agent_scores — this agent returns a bespoke trade-thesis schema instead.
import httpx
import json
import logging
from config import (get_settings, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL_HEAVY, estimate_deepseek_cost)
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()

CACHE_KEY = "technical_fusion_signal"
CACHE_TTL = 360  # 6 min — outlasts the 5-min scheduler interval


def _validate_entry_zone(result: dict, live_price: float) -> dict:
    """
    Reject any trade recommendation whose entry zone is unreachably far from the
    current live price — this catches hallucinated / stale levels.

    Tolerance: entry midpoint must be within 1.5 % of live_price.
    If it falls outside that band, the thesis is zeroed out as unreliable.
    """
    if not live_price or live_price <= 0:
        return result
    direction = result.get("direction", "NEUTRAL")
    if direction == "NEUTRAL":
        return result

    entry_zone = str(result.get("entry_zone", ""))
    try:
        parts = [
            float(p.replace(",", "").strip())
            for p in entry_zone.replace("$", "").split("-")
            if p.strip()
        ]
        if not parts:
            return result
        entry_lo  = min(parts)
        entry_hi  = max(parts)
        entry_mid = (entry_lo + entry_hi) / 2
    except Exception:
        return result

    pct_away = abs(entry_mid - live_price) / live_price * 100
    MAX_PCT  = 1.5  # beyond 1.5 % = stale / hallucinated entry

    if pct_away > MAX_PCT:
        logger.warning(
            f"[fusion_validate] Entry zone {entry_zone} is {pct_away:.2f}% from live "
            f"price ${live_price:.2f} (max {MAX_PCT}%) — nullifying trade"
        )
        result["direction"]    = "NEUTRAL"
        result["setup_quality"] = "NO_TRADE"
        result["probability"]  = 0
        result["entry_error"]  = (
            f"Entry zone {entry_zone} is {pct_away:.1f}% away from live price "
            f"${live_price:.2f} — rejected (possible hallucination)"
        )
    return result


def _validate_targets(result: dict) -> dict:
    """
    Sanity-check that targets are on the correct side of the entry zone.
    SHORT → targets must be BELOW entry low.
    LONG  → targets must be ABOVE entry high.
    If invalid, nulls out the bad target and flags result["target_error"].
    """
    direction = result.get("direction", "NEUTRAL")
    if direction == "NEUTRAL":
        return result

    # Parse entry zone — expected format "4282.11-4289.59" or a single price
    entry_zone = str(result.get("entry_zone", ""))
    try:
        parts = [float(p.replace(",", "").strip()) for p in entry_zone.replace("$", "").split("-") if p.strip()]
        entry_lo = min(parts)
        entry_hi = max(parts)
    except Exception:
        return result   # can't parse entry zone — skip validation

    errors = []
    for key in ("first_target", "second_target"):
        raw = result.get(key)
        if not raw:
            continue
        try:
            tp = float(str(raw).replace("$", "").replace(",", "").split()[0])
        except Exception:
            continue

        if direction == "SHORT" and tp > entry_lo:
            logger.warning(f"[fusion_validate] SHORT target {key}={tp} is ABOVE entry low {entry_lo} — nulling")
            result[key] = None
            errors.append(f"{key} {tp} above SHORT entry {entry_lo}")
        elif direction == "LONG" and tp < entry_hi:
            logger.warning(f"[fusion_validate] LONG target {key}={tp} is BELOW entry high {entry_hi} — nulling")
            result[key] = None
            errors.append(f"{key} {tp} below LONG entry {entry_hi}")

    if errors:
        result["target_error"] = "Invalid targets removed: " + "; ".join(errors)
        logger.error(f"[fusion_validate] direction={direction} entry={entry_zone} | {result['target_error']}")

    return result


class TechnicalFusionAgent:
    """Senior-trader fusion of deterministic SMC structure with fundamentals.
    Trusts the SMC engine's price levels verbatim — never recalculates them."""

    agent_name = "technical_fusion"
    cache_ttl  = CACHE_TTL

    async def collect_data(self) -> dict:
        import asyncio
        from datetime import datetime, timezone
        from engines.patterns_engine import analyze_all
        from engines.macro_bias import get_macro_bias
        from services.supabase_service import get_latest_agent_scores, get_latest_forecast
        from services.kronos_client import get_kronos_all_timeframes
        from services.kronos_tracker import get_accuracy_stats, log_forecast
        from collectors.oanda_collector import OandaCollector

        oanda = OandaCollector()

        # ── Step 1: Grab the live gold price BEFORE anything else ─────────────
        # Priority: cTrader Redis (most live) → OANDA REST (30s cache) → SMC close
        live_price      = None
        live_price_src  = "unknown"
        try:
            ct_data = await cache_get("live_xauusd_price")
            if ct_data:
                raw_p = ct_data.get("price") or ct_data.get("bid") or ct_data.get("mid")
                if raw_p and float(raw_p) > 500:
                    live_price     = round(float(raw_p), 2)
                    live_price_src = "cTrader"
        except Exception:
            pass

        if not live_price:
            try:
                oanda_price = await oanda.get_gold_price()
                if oanda_price.get("price", 0) > 500:
                    live_price     = oanda_price["price"]
                    live_price_src = "OANDA"
            except Exception:
                pass

        smc, agents, forecast, mbs, accuracy = await asyncio.gather(
            analyze_all(),
            get_latest_agent_scores(),
            get_latest_forecast(),
            get_macro_bias(),
            get_accuracy_stats(),
        )

        # Final fallback: use current_price from the SMC engine (open candle close)
        if not live_price:
            try:
                live_price     = float(smc.get("15min", {}).get("current_price", 0) or 0) or None
                live_price_src = "smc_open_candle"
            except Exception:
                pass

        live_price_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        logger.info(f"[technical_fusion] live_price=${live_price} src={live_price_src} ts={live_price_ts}")

        # ── Fetch OANDA candles for Kronos (each TF in parallel) ─────────────
        candles_by_tf = {}
        for tf, gran, count in [('15min', 'M15', 200), ('1h', 'H1', 200), ('4h', 'H4', 100)]:
            try:
                raw = await oanda.get_candles('XAU_USD', gran, count)
                candles_by_tf[tf] = [
                    {'open': float(c['open']), 'high': float(c['high']),
                     'low': float(c['low']),  'close': float(c['close']),
                     'volume': int(c.get('volume', 0)), 'time': c['time']}
                    for c in raw if c.get('complete', True)
                ]
            except Exception:
                candles_by_tf[tf] = []

        kronos = await get_kronos_all_timeframes(candles_by_tf)

        # Log Kronos forecasts for accuracy tracking
        entry_price = float(forecast.get('gold_price', 0)) if forecast else 0.0
        for tf, fc in kronos.items():
            if fc.get('available'):
                await log_forecast(fc, tf, entry_price)

        fundamentals = {s.get("agent_name"): {"score": s.get("score"), "bias": s.get("raw_data", {}).get("directional_bias")}
                        for s in (agents or [])}
        return {
            "smc":             smc,
            "kronos":          kronos,
            "kronos_accuracy": accuracy,
            "fundamentals":    fundamentals,
            "mbs":             mbs,
            "regime":          forecast.get("macro_regime") if forecast else "unknown",
            "live_price":      live_price,
            "live_price_src":  live_price_src,
            "live_price_ts":   live_price_ts,
        }

    def build_prompt(self, data: dict) -> str:
        live_price = data.get("live_price")
        live_src   = data.get("live_price_src", "unknown")
        live_ts    = data.get("live_price_ts", "")

        if live_price:
            price_header = (
                f"══════════════════════════════════════════\n"
                f"  CURRENT LIVE GOLD PRICE: ${live_price:.2f}\n"
                f"  Source: {live_src}  |  Fetched: {live_ts}\n"
                f"  THIS IS THE GROUND TRUTH — every level in your JSON\n"
                f"  MUST make directional sense relative to ${live_price:.2f}.\n"
                f"══════════════════════════════════════════"
            )
        else:
            price_header = (
                "⚠ LIVE PRICE UNAVAILABLE — use SMC current_price as reference.\n"
                "  Be extra conservative; set setup_quality to WEAK at best."
            )

        # Build Kronos section dynamically
        kronos_lines = []
        for tf, fc in (data.get('kronos') or {}).items():
            if not fc.get('available'):
                continue
            acc       = data.get('kronos_accuracy', {}).get(tf, {})
            trusted   = acc.get('trusted', False)
            hit_rate  = acc.get('hit_rate')
            note      = acc.get('note', 'insufficient data')
            weight_note = (
                f"[TRUSTED — {hit_rate}% directional hit rate over {acc.get('n')} forecasts]"
                if trusted else
                f"[UNPROVEN — {note} — treat as weak signal only]"
            )
            move = fc.get('expected_move_pts', 0)
            kronos_lines.append(
                f"  {tf.upper()}: predicts {fc.get('direction', '?')} → {fc.get('predicted_close')} "
                f"({move:+.2f} pts) by {fc.get('target_time', '?')} "
                f"[range {fc.get('predicted_low')}–{fc.get('predicted_high')}] {weight_note}"
            )
        if kronos_lines:
            kronos_section = "KRONOS PROBABILISTIC FORECAST (time-series model, separate from SMC):\n" + "\n".join(kronos_lines)
        else:
            kronos_section = "KRONOS: offline — disregard this section"

        price_rules = ""
        if live_price:
            price_rules = (
                f"- LIVE PRICE ANCHOR: The current gold price is ${live_price:.2f}. "
                f"Your entry_zone MUST be within 1.5% of this price (i.e. roughly "
                f"${live_price * 0.985:.2f}–${live_price * 1.015:.2f}). "
                f"If no SMC level falls in that band, return NEUTRAL / NO_TRADE.\n"
                f"- For LONG: entry_zone lower bound must be ≤ ${live_price:.2f} or price must be approaching it from below.\n"
                f"- For SHORT: entry_zone upper bound must be ≥ ${live_price:.2f} or price must be approaching it from above.\n"
                f"- NEVER place an entry zone 30+ points away from ${live_price:.2f} unless an explicit SMC level is shown at that price in the data.\n"
            )

        return f"""{price_header}

You are a senior gold (XAUUSD) trader fusing Smart Money Concepts price-action with macro fundamentals.

The SMC data below is from a deterministic engine — TRUST the patterns and price levels, do not recalculate.

SMC PATTERNS (15m/1h/4h) — net_confluence -5 bearish .. +5 bullish:
{json.dumps(data['smc'], indent=2)}

{kronos_section}

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

Rules:
{price_rules}- Every price level must come from the SMC data provided above — never invent levels.
- If you are not certain a level exists in the SMC data, omit it (set that field to null) rather than estimate.
- CRITICAL: For SHORT trades, first_target and second_target MUST be BELOW the entry_zone lower bound. For LONG trades, targets MUST be ABOVE the entry_zone upper bound. A target on the wrong side of entry is never valid.
- If SMC and fundamentals conflict, say so and lower probability.
- If net_confluence is between -1 and +1, default to NO_TRADE.
- If Kronos is UNPROVEN, treat its direction as a very weak tiebreaker only, not a primary signal. If TRUSTED (≥55% hit rate, n≥20), give it meaningful weight alongside the SMC structure.
- Score your own confidence honestly. When in doubt, return NO_TRADE with a clear reasoning — do not hallucinate a setup."""

    async def _call_deepseek(self, prompt: str) -> tuple[dict, str]:
        """DeepSeek Reasoner via OpenAI-compatible API."""
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")

        DS_MODEL = DEEPSEEK_MODEL_HEAVY   # deepseek-reasoner
        payload = {
            "model":      DS_MODEL,
            "max_tokens": 6000,
            "messages": [
                {"role": "system", "content": "You are a precise, honest trading analyst. Respond with raw JSON only — no markdown, no preamble, no explanation before or after the JSON."},
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
        # deepseek-chat puts answer in content; reasoner may put it in reasoning_content
        raw = (msg.get("content") or msg.get("reasoning_content") or "").strip()

        if not raw:
            raise ValueError(f"DeepSeek returned empty content. Full response: {json.dumps(data)[:500]}")

        # Strip any markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
            raw = raw.strip()

        # Strip any leading/trailing non-JSON text (find first '{' and last '}')
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        usage   = data.get("usage", {})
        in_tok  = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost    = estimate_deepseek_cost(DS_MODEL, in_tok, out_tok)
        result  = json.loads(raw)
        logger.info(
            f"[technical_fusion/deepseek-reasoner] {result.get('direction')} | "
            f"quality={result.get('setup_quality')} | prob={result.get('probability')}% | "
            f"in={in_tok} out={out_tok} cost=${cost:.5f}"
        )
        return result, "deepseek_reasoner"

    async def run(self) -> dict:
        cached = await cache_get(CACHE_KEY)
        if cached:
            return cached

        try:
            data   = await self.collect_data()
            prompt = self.build_prompt(data)
        except Exception as e:
            logger.error(f"[technical_fusion] data collection error: {e}")
            return {"direction": "NEUTRAL", "probability": 0, "setup_quality": "NO_TRADE",
                    "reasoning": f"Data collection error: {e}", "error": str(e)}

        live_price = data.get("live_price")
        result     = None
        provider   = None

        try:
            result, provider = await self._call_deepseek(prompt)
        except Exception as ds_err:
            logger.error(f"[technical_fusion] DeepSeek failed: {ds_err}")
            return {"direction": "NEUTRAL", "probability": 0, "setup_quality": "NO_TRADE",
                    "reasoning": f"DeepSeek error: {ds_err}", "error": str(ds_err)}

        # ── Sanity checks ─────────────────────────────────────────────────────
        # 1. Entry zone must be near the live price (catches stale / hallucinated entries)
        result = _validate_entry_zone(result, live_price)
        # 2. Targets must be on the correct side of entry
        result = _validate_targets(result)

        from datetime import datetime, timezone
        result["generated_at"]   = datetime.now(timezone.utc).isoformat()
        result["cache_ttl_s"]    = self.cache_ttl
        result["provider"]       = provider
        result["live_price_used"] = live_price        # expose for UI transparency
        result["live_price_src"]  = data.get("live_price_src")

        await cache_set(CACHE_KEY, result, ttl_seconds=self.cache_ttl)
        return result
