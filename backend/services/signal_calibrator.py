# backend/services/signal_calibrator.py
"""
Computes rolling 30-day statistics from OANDA H1 data.
Used to properly scale tanh transformation inputs / replace hardcoded
"significant move" thresholds with real, computed standard deviations.
Runs once per day at market close (22:00 UTC). Cached in Supabase (24h).
"""
from services.redis_service import cache_get, cache_set
from collectors.oanda_collector import OandaCollector
import statistics
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "signal_calibration_30d"


async def compute_calibration() -> dict:
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    try:
        oanda = OandaCollector()

        # Fetch ~30 days of H1 gold candles (720 bars) — stays within free-tier limits
        candles = await oanda.get_candles("XAU_USD", "H1", 720)

        if len(candles) < 48:
            return {"status": "insufficient_data", "bars": len(candles)}

        # Hourly returns (simple-return approximation, in %)
        returns = []
        for i in range(1, len(candles)):
            prev = candles[i - 1]["close"]
            curr = candles[i]["close"]
            if prev > 0:
                returns.append((curr - prev) / prev * 100)

        if len(returns) < 24:
            return {"status": "insufficient_returns"}

        # 4-hour volatility (group into 4-bar windows)
        four_h_returns = []
        for i in range(0, len(returns) - 3, 4):
            chunk = returns[i:i + 4]
            four_h_returns.append(sum(chunk))

        gold_std_1h  = round(statistics.stdev(returns), 4)        if len(returns) > 1        else 0.5
        gold_std_4h  = round(statistics.stdev(four_h_returns), 4) if len(four_h_returns) > 1 else 1.0

        abs_returns  = [abs(r) for r in returns]
        avg_abs_move = round(statistics.mean(abs_returns), 4)

        # DXY momentum proxy: OANDA has no direct DXY instrument — use EUR_USD
        # (most heavily-weighted DXY component) returns as a liquidity proxy.
        eur_candles    = await oanda.get_candles("EUR_USD", "H1", 720)
        eurusd_returns = []
        for i in range(1, len(eur_candles)):
            prev = eur_candles[i - 1]["close"]
            curr = eur_candles[i]["close"]
            if prev > 0:
                eurusd_returns.append((curr - prev) / prev * 100)

        dxy_proxy_std = round(statistics.stdev(eurusd_returns), 5) if len(eurusd_returns) > 1 else 0.05

        calibration = {
            "status":           "calibrated",
            "bars_used":        len(candles),
            "returns_computed": len(returns),

            # Gold volatility
            "gold_std_1h":      gold_std_1h,
            "gold_std_4h":      gold_std_4h,
            "gold_avg_abs_1h":  avg_abs_move,

            # DXY proxy (EURUSD)
            "dxy_proxy_std_1h": dxy_proxy_std,

            # Derived thresholds (replace hardcoded values) —
            # a move is "significant" if it exceeds 0.5 standard deviations
            "significant_gold_move_1h": round(gold_std_1h   * 0.5, 4),
            "significant_gold_move_4h": round(gold_std_4h   * 0.5, 4),
            "significant_dxy_move":     round(dxy_proxy_std * 0.5, 5),

            "calibrated_at": datetime.now(timezone.utc).isoformat(),
        }

        await cache_set(CACHE_KEY, calibration, ttl_seconds=86400)
        logger.info(f"Calibration: gold_std_4h={gold_std_4h:.4f} dxy_proxy_std={dxy_proxy_std:.5f}")
        return calibration

    except Exception as e:
        logger.error(f"Calibration error: {e}")
        return {"status": "error", "error": str(e)}
