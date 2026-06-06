# backend/engines/alert_engine.py
from services.supabase_service import insert_alert
from services.websocket_manager import ws_manager
from config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class AlertEngine:

    async def check_and_fire(self, new_forecast: dict, old_forecast: dict | None):
        if not old_forecast:
            return

        alerts = []

        # ── Probability Shift ──────────────────────────────────────────────
        bull_change = abs(
            new_forecast.get("bullish_prob", 0) - old_forecast.get("bullish_prob", 0)
        )
        if bull_change >= settings.probability_alert_threshold:
            direction = (
                "increased"
                if new_forecast["bullish_prob"] > old_forecast["bullish_prob"]
                else "decreased"
            )
            alerts.append({
                "alert_type": "probability_shift",
                "severity": "high" if bull_change >= 20 else "medium",
                "title": f"Bullish Probability {direction.capitalize()} by {bull_change:.1f}%",
                "description": (
                    f"Shifted from {old_forecast['bullish_prob']:.1f}% "
                    f"to {new_forecast['bullish_prob']:.1f}%"
                ),
                "metadata": {
                    "old_prob": old_forecast["bullish_prob"],
                    "new_prob": new_forecast["bullish_prob"],
                    "change": bull_change,
                },
            })

        # ── Regime Change ──────────────────────────────────────────────────
        if new_forecast.get("macro_regime") != old_forecast.get("macro_regime"):
            alerts.append({
                "alert_type": "regime_change",
                "severity": "critical",
                "title": (
                    f"Regime Change: {old_forecast.get('macro_regime')} "
                    f"→ {new_forecast.get('macro_regime')}"
                ),
                "description": "Macro regime has shifted. All forecasts recalculated.",
                "metadata": {
                    "from_regime": old_forecast.get("macro_regime"),
                    "to_regime": new_forecast.get("macro_regime"),
                },
            })

        # ── Confidence Shift ───────────────────────────────────────────────
        conf_change = abs(
            new_forecast.get("confidence_score", 0)
            - old_forecast.get("confidence_score", 0)
        )
        if conf_change >= settings.confidence_alert_threshold:
            alerts.append({
                "alert_type": "confidence_shift",
                "severity": "medium",
                "title": f"Model Confidence Changed by {conf_change:.0f}%",
                "description": (
                    f"Confidence shifted from {old_forecast['confidence_score']:.0f}% "
                    f"to {new_forecast['confidence_score']:.0f}%"
                ),
                "metadata": {"change": conf_change},
            })

        # ── Momentum Flip ──────────────────────────────────────────────────
        old_mom = old_forecast.get("forecast_momentum", 0)
        new_mom = new_forecast.get("forecast_momentum", 0)
        if (old_mom > 0 and new_mom < -5) or (old_mom < 0 and new_mom > 5):
            alerts.append({
                "alert_type": "momentum_flip",
                "severity": "high",
                "title": f"Forecast Momentum Reversed: {old_mom:+.1f} → {new_mom:+.1f}",
                "description": "Bullish/bearish momentum has reversed direction.",
                "metadata": {"old_momentum": old_mom, "new_momentum": new_mom},
            })

        for alert in alerts:
            await insert_alert(alert)
            await ws_manager.send_alert(alert)
            logger.warning(f"ALERT [{alert['severity'].upper()}]: {alert['title']}")
