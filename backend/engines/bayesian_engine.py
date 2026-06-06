# backend/engines/bayesian_engine.py
from typing import Dict, List
from datetime import datetime
import logging
from services.supabase_service import insert_forecast, get_latest_forecast
from services.websocket_manager import ws_manager
from services.redis_service import cache_set
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class BayesianEngine:
    """
    Core probabilistic forecasting engine.
    Converts weighted agent scores into probability distributions
    conditioned on the current macro regime.
    """

    PRIOR_BULL    = 0.34
    PRIOR_BEAR    = 0.33
    PRIOR_NEUTRAL = 0.33

    REGIME_PRIORS = {
        "inflation_shock":       {"bull": 0.65, "bear": 0.20, "neutral": 0.15},
        "disinflation":          {"bull": 0.25, "bear": 0.55, "neutral": 0.20},
        "recession_risk":        {"bull": 0.60, "bear": 0.20, "neutral": 0.20},
        "growth_expansion":      {"bull": 0.25, "bear": 0.50, "neutral": 0.25},
        "liquidity_expansion":   {"bull": 0.55, "bear": 0.25, "neutral": 0.20},
        "liquidity_contraction": {"bull": 0.25, "bear": 0.55, "neutral": 0.20},
        "rate_hike_cycle":       {"bull": 0.20, "bear": 0.60, "neutral": 0.20},
        "rate_cut_cycle":        {"bull": 0.60, "bear": 0.20, "neutral": 0.20},
        "geopolitical_crisis":   {"bull": 0.65, "bear": 0.15, "neutral": 0.20},
        "risk_off":              {"bull": 0.60, "bear": 0.20, "neutral": 0.20},
    }

    VOLATILITY_BY_REGIME = {
        "inflation_shock":     1.8,
        "geopolitical_crisis": 2.2,
        "risk_off":            1.9,
        "rate_cut_cycle":      1.3,
        "growth_expansion":    0.8,
        "disinflation":        0.9,
        "rate_hike_cycle":     1.2,
        "recession_risk":      1.6,
        "liquidity_expansion": 1.0,
        "liquidity_contraction": 1.1,
    }

    async def compute(
        self,
        agent_scores: List[Dict],
        current_regime: str,
        gold_price: float
    ) -> dict:
        if not agent_scores:
            return await self._default_forecast(gold_price)

        weights = settings.agent_weights
        weighted_score = 0.0
        total_weight   = 0.0
        confidence_sum = 0.0

        for score_obj in agent_scores:
            agent_name = score_obj.get("agent_name", "").replace("_agent", "")
            weight = weights.get(agent_name, 0.05)
            score  = score_obj.get("score", 0)
            conf   = score_obj.get("confidence", 50) / 100.0
            weighted_score += score * weight * conf
            total_weight   += weight * conf
            confidence_sum += conf

        composite_score = (weighted_score / total_weight) if total_weight > 0 else 0.0
        avg_confidence  = (confidence_sum / len(agent_scores)) * 100 if agent_scores else 50.0

        priors = self.REGIME_PRIORS.get(current_regime, {
            "bull": self.PRIOR_BULL,
            "bear": self.PRIOR_BEAR,
            "neutral": self.PRIOR_NEUTRAL
        })

        score_n      = composite_score / 100.0   # normalise to -1..+1
        bull_like    = (1 + score_n) / 2
        bear_like    = (1 - score_n) / 2
        neutral_like = 1 - abs(score_n)

        bull_post    = priors["bull"]    * bull_like
        bear_post    = priors["bear"]    * bear_like
        neutral_post = priors["neutral"] * neutral_like
        total        = bull_post + bear_post + neutral_post

        bull_prob    = (bull_post    / total) * 100
        bear_prob    = (bear_post    / total) * 100
        neutral_prob = (neutral_post / total) * 100

        prev = await get_latest_forecast()
        momentum = (bull_prob - prev.get("bullish_prob", 34)) if prev else 0.0

        vol_mult   = self.VOLATILITY_BY_REGIME.get(current_regime, 1.0)
        base_range = gold_price * 0.012 * vol_mult
        bias       = score_n * 0.3

        def biased_range(mult):
            low    = gold_price - base_range * mult
            high   = gold_price + base_range * mult
            center = (low + high) / 2
            spread = (high - low) / 2
            return (
                round(center + bias * spread - spread, 2),
                round(center + bias * spread + spread, 2),
            )

        r4h  = biased_range(0.5)
        r24h = biased_range(1.0)
        r1w  = biased_range(2.5)
        r1m  = biased_range(5.0)
        r1q  = biased_range(10.0)

        forecast = {
            "gold_price":            round(gold_price, 2),
            "bullish_prob":          round(bull_prob, 2),
            "bearish_prob":          round(bear_prob, 2),
            "neutral_prob":          round(neutral_prob, 2),
            "confidence_score":      round(avg_confidence, 2),
            "forecast_momentum":     round(momentum, 2),
            "macro_regime":          current_regime,
            "agent_scores":          {s.get("agent_name"): s.get("score") for s in agent_scores},
            "range_4h_low":          r4h[0],   "range_4h_high":  r4h[1],
            "range_24h_low":         r24h[0],  "range_24h_high": r24h[1],
            "range_1w_low":          r1w[0],   "range_1w_high":  r1w[1],
            "range_1m_low":          r1m[0],   "range_1m_high":  r1m[1],
            "range_1q_low":          r1q[0],   "range_1q_high":  r1q[1],
            "volatility_score":      round(vol_mult * 50, 2),
            "tail_risk_upside":      round(gold_price * (1 + 0.08 * vol_mult), 2),
            "tail_risk_downside":    round(gold_price * (1 - 0.08 * vol_mult), 2),
            "tail_risk_probability": round(10.0 + abs(score_n) * 10, 2),
            "timestamp":             datetime.utcnow().isoformat(),
        }

        await insert_forecast(forecast)
        await cache_set("latest_forecast", forecast, ttl_seconds=60)
        await ws_manager.send_forecast_update(forecast)

        logger.info(
            f"Forecast | Bull: {bull_prob:.1f}% Bear: {bear_prob:.1f}% "
            f"Neutral: {neutral_prob:.1f}% | Conf: {avg_confidence:.0f}% | {current_regime}"
        )
        return forecast

    async def _default_forecast(self, gold_price: float) -> dict:
        return {
            "gold_price": gold_price, "bullish_prob": 34.0,
            "bearish_prob": 33.0, "neutral_prob": 33.0,
            "confidence_score": 10.0, "forecast_momentum": 0.0,
            "macro_regime": "unknown",
            "timestamp": datetime.utcnow().isoformat(),
        }
