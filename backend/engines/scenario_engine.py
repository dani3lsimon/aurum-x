# backend/engines/scenario_engine.py
# Anthropic SDK — generates 3 probability-weighted gold scenario paths — HAIKU
import anthropic
import json
import asyncio
import logging
from services.supabase_service import get_supabase
from config import get_settings, MODEL_HAIKU, MAX_TOKENS_SCENARIO, estimate_cost

logger = logging.getLogger(__name__)
settings = get_settings()

# Anthropic client — ANTHROPIC_API_KEY from environment
client = anthropic.Anthropic()

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
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=MODEL_HAIKU,
                    max_tokens=MAX_TOKENS_SCENARIO,
                    system=SCENARIO_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            cost = estimate_cost(MODEL_HAIKU, response.usage.input_tokens, response.usage.output_tokens)
            logger.info(f"[scenario_engine] tokens in={response.usage.input_tokens} out={response.usage.output_tokens} estimated_cost=${cost:.5f}")

            raw_text = response.content[0].text
            data = json.loads(raw_text)
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
