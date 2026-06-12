# backend/engines/scenario_engine.py
# DeepSeek Reasoner — generates 3 probability-weighted gold scenario paths
import httpx
import json
import logging
from services.supabase_service import get_supabase
from config import get_settings, MAX_TOKENS_SCENARIO, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL_HEAVY, estimate_deepseek_cost

logger = logging.getLogger(__name__)
settings = get_settings()

SCENARIO_SYSTEM_PROMPT = """Generate a JSON object with key "scenarios" containing exactly 3 scenario objects.
Each object: label (A/B/C), scenario_name (5-8 words), probability (int, sum=100), gold_target_4h, gold_target_24h, gold_target_1w, gold_target_1m, confidence (0-100), key_drivers (3-5 strings), narrative (2 sentences).
Return only JSON. No preamble."""


class ScenarioEngine:
    """
    Generates 3 probability-weighted future gold paths using Claude.
    Runs after each major forecast update (every 2 hours).
    """

    async def generate(self, forecast: dict, agent_scores: list) -> list:
        prompt = f"""Generate a 3-scenario probability tree for XAUUSD based on current conditions.

Current State:
- Gold Price: ${forecast.get('gold_price', 'unknown')}
- Bullish Probability: {forecast.get('bullish_prob', 0):.1f}%
- Bearish Probability: {forecast.get('bearish_prob', 0):.1f}%
- Macro Regime: {forecast.get('macro_regime', 'unknown')}
- Forecast Momentum: {forecast.get('forecast_momentum', 0):.1f}
- Model Confidence: {forecast.get('confidence_score', 0):.0f}%
- Volatility Score: {forecast.get('volatility_score', 50):.1f}

Agent Score Landscape:
{json.dumps(forecast.get('agent_scores', {}), indent=2)}

Price Ranges:
- 4H range: ${forecast.get('range_4h_low', 0):.2f} – ${forecast.get('range_4h_high', 0):.2f}
- 1W range: ${forecast.get('range_1w_low', 0):.2f} – ${forecast.get('range_1w_high', 0):.2f}

Tail Risk:
- Upside tail: ${forecast.get('tail_risk_upside', 0):.2f}
- Downside tail: ${forecast.get('tail_risk_downside', 0):.2f}

Create three distinct scenarios covering the most likely paths for gold over the next month.
Probabilities must sum to exactly 100."""

        try:
            payload = {
                "model": DEEPSEEK_MODEL_HEAVY,
                "max_tokens": MAX_TOKENS_SCENARIO,
                "messages": [
                    {"role": "system", "content": SCENARIO_SYSTEM_PROMPT},
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
                response_data = resp.json()

            msg      = response_data["choices"][0]["message"]
            raw_text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
            usage    = response_data.get("usage", {})
            cost     = estimate_deepseek_cost(DEEPSEEK_MODEL_HEAVY,
                                              usage.get("prompt_tokens", 0),
                                              usage.get("completion_tokens", 0))
            logger.info(f"[scenario_engine] tokens in={usage.get('prompt_tokens',0)} out={usage.get('completion_tokens',0)} estimated_cost=${cost:.5f}")

            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            start = raw_text.find("{"); end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                raw_text = raw_text[start:end]
            data = json.loads(raw_text.strip())
            scenarios = data.get("scenarios", data if isinstance(data, list) else [])

            if forecast.get("id") and scenarios:
                sb = get_supabase()
                records = []
                for sc in scenarios:
                    records.append({
                        "forecast_id":         forecast["id"],
                        "scenario_label":      sc.get("label", ""),
                        "scenario_name":       sc.get("scenario_name", ""),
                        "probability":         sc.get("probability", 0),
                        "expected_gold_target":sc.get("gold_target_1m", 0),
                        "confidence":          sc.get("confidence", 50),
                        "key_drivers":         sc.get("key_drivers", []),
                        "horizon":             "1 month",
                    })
                sb.table("scenarios").insert(records).execute()

            logger.info(f"Scenario engine generated {len(scenarios)} scenarios")
            return scenarios

        except json.JSONDecodeError as e:
            logger.error(f"Scenario JSON parse error: {e}")
            return []
        except Exception as e:
            logger.error(f"Scenario engine error: {e}")
            return []
