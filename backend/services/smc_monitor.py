# backend/services/smc_monitor.py
"""
SMC Change Monitor — runs on the APScheduler every 30 seconds.

Compares the latest SMC alignment + Fusion direction/quality against the
previously-seen snapshot stored in Redis. When anything material changes
(direction flip, alignment shift, setup_quality change) it broadcasts a
WebSocket event so the frontend can show a live alert without the user
needing to refresh.

This is intentionally lightweight — it just reads the two cached results
(already computed by TechnicalPanel's 30s poll) and diffs them. No new
AI calls, no extra cost.
"""
import logging
from datetime import datetime, timezone

from services.redis_service import cache_get, cache_set
from services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Key for persisting the last-known snapshot between scheduler ticks
_SNAPSHOT_KEY = "smc_monitor_snapshot"


async def check_for_changes() -> dict | None:
    """
    Compare current SMC + Fusion results against the last snapshot.
    Returns a change-event dict if something material changed, else None.
    Broadcasts the event over WebSocket so the frontend is notified instantly.
    """
    try:
        smc    = await cache_get("smc_patterns_all_tf")
        fusion = await cache_get("technical_fusion_signal")

        if not smc or not fusion:
            return None   # data not ready yet

        current = {
            "smc_alignment":   smc.get("alignment"),
            "smc_net":         round(float(smc.get("net_confluence") or 0), 2),
            "fusion_dir":      fusion.get("direction"),
            "fusion_quality":  fusion.get("setup_quality"),
            "fusion_prob":     fusion.get("probability"),
            "smc_fetched_at":  smc.get("fetched_at"),
            "fusion_gen_at":   fusion.get("generated_at"),
        }

        prev = await cache_get(_SNAPSHOT_KEY)

        changes: list[dict] = []

        if prev:
            # SMC alignment flip
            if current["smc_alignment"] != prev.get("smc_alignment"):
                changes.append({
                    "field":   "smc_alignment",
                    "from":    prev.get("smc_alignment"),
                    "to":      current["smc_alignment"],
                    "label":   "⌬ SMC Alignment changed",
                    "urgent":  True,
                })

            # Fusion direction flip (most important)
            if current["fusion_dir"] != prev.get("fusion_dir"):
                changes.append({
                    "field":  "fusion_direction",
                    "from":   prev.get("fusion_dir"),
                    "to":     current["fusion_dir"],
                    "label":  "⚡ Fusion direction flipped",
                    "urgent": True,
                })

            # Setup quality change (e.g. NO_TRADE → HIGH_CONVICTION)
            if current["fusion_quality"] != prev.get("fusion_quality"):
                changes.append({
                    "field":  "setup_quality",
                    "from":   prev.get("fusion_quality"),
                    "to":     current["fusion_quality"],
                    "label":  "⚡ Setup quality changed",
                    "urgent": current["fusion_quality"] in ("HIGH_CONVICTION", "SCALP"),
                })

            # Net confluence crossed a threshold (±2.0 = meaningful zone boundary)
            prev_net = float(prev.get("smc_net") or 0)
            curr_net = float(current["smc_net"] or 0)
            crossed_thresholds = [t for t in [-3.0, -1.0, 1.0, 3.0]
                                   if (prev_net < t <= curr_net) or (curr_net < t <= prev_net)]
            for t in crossed_thresholds:
                direction = "↑" if curr_net > prev_net else "↓"
                changes.append({
                    "field":  "net_confluence",
                    "from":   prev_net,
                    "to":     curr_net,
                    "label":  f"⌬ Net confluence {direction} crossed {t:+.1f}",
                    "urgent": abs(t) >= 3.0,
                })

        # Always update the snapshot
        await cache_set(_SNAPSHOT_KEY, current, ttl_seconds=3600)

        if changes and prev:
            event = {
                "type":      "smc_change",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "changes":   changes,
                "current":   current,
            }
            await ws_manager.broadcast(event)
            logger.info(f"SMC monitor: {len(changes)} change(s) — {[c['label'] for c in changes]}")
            return event

    except Exception as e:
        logger.warning(f"SMC monitor error: {e}")

    return None
