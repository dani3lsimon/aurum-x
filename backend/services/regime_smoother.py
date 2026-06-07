# backend/services/regime_smoother.py
"""
Smooths the instantaneous regime_agent output into a stable regime label.

Rules:
- Collect last 24 hours of regime classifications from regime_history table
- Current smoothed regime = mode (most frequent label) in that window
- Hysteresis: do not switch from current smoothed regime unless the
  challenger has appeared in >70% of the last 4 entries consecutively
- If no 24h data: fall back to latest single regime label
- Cache result 30 minutes in Supabase
"""
from services.supabase_service import get_supabase
from services.redis_service import cache_get, cache_set
from datetime import datetime, timedelta, timezone
from collections import Counter
import logging

logger = logging.getLogger(__name__)


async def get_smoothed_regime() -> dict:
    cache_key = "smoothed_regime"
    cached    = await cache_get(cache_key)
    if cached:
        return cached

    try:
        sb  = get_supabase()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        result = sb.table("regime_history")\
            .select("primary_regime, timestamp")\
            .gte("timestamp", cutoff)\
            .order("timestamp", desc=True)\
            .limit(96)\
            .execute()

        rows = result.data if result.data else []

        if not rows:
            return {"regime": "unknown", "confidence": 0, "method": "no_data", "sample_size": 0}

        labels     = [r["primary_regime"] for r in rows if r.get("primary_regime")]
        counts     = Counter(labels)
        total      = len(labels)
        mode_label = counts.most_common(1)[0][0]
        mode_pct   = counts[mode_label] / total

        # Hysteresis check: get current stored smoothed regime
        stored = await cache_get("smoothed_regime_locked")
        current_locked = stored.get("regime") if stored else None

        if current_locked and current_locked != mode_label:
            # Check if challenger holds last 4 consecutive entries
            last_4 = labels[:4]
            challenger_consecutive = all(l == mode_label for l in last_4)
            challenger_pct_last_4  = last_4.count(mode_label) / len(last_4) if last_4 else 0

            if not (challenger_consecutive and challenger_pct_last_4 >= 0.70):
                # Hysteresis blocks the switch — keep current locked regime
                output = {
                    "regime":        current_locked,
                    "challenger":    mode_label,
                    "confidence":    round(mode_pct * 100, 1),
                    "blocked_by_hysteresis": True,
                    "method":        "hysteresis_hold",
                    "sample_size":   total,
                    "window_hours":  24,
                }
                await cache_set(cache_key, output, ttl_seconds=1800)
                return output

        # Switch is allowed — update locked regime
        output = {
            "regime":        mode_label,
            "confidence":    round(mode_pct * 100, 1),
            "blocked_by_hysteresis": False,
            "method":        "24h_rolling_mode",
            "sample_size":   total,
            "window_hours":  24,
            "top_labels":    dict(counts.most_common(3)),
        }
        await cache_set("smoothed_regime_locked", output, ttl_seconds=3600)
        await cache_set(cache_key, output, ttl_seconds=1800)
        logger.info(f"Smoothed regime: {mode_label} ({mode_pct*100:.0f}% of 24h window, n={total})")
        return output

    except Exception as e:
        logger.error(f"Regime smoother error: {e}")
        return {"regime": "unknown", "confidence": 0, "method": "error"}
