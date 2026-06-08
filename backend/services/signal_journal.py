# backend/services/signal_journal.py
"""
Signal Journal — records every generated signal and tracks outcomes.
Called by multi_tf_engine when a new signal fires.
Called by the price monitor on every tick to check outcomes.
"""
import logging
from datetime import datetime, timezone
from services.supabase_service import get_supabase

logger = logging.getLogger(__name__)


def generate_signal_id(direction: str, timeframe: str) -> str:
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    return f"{direction}_{timeframe}_{ts}"


async def record_signal(multi_tf_result: dict) -> str | None:
    """
    Record a new signal to signal_history.
    Called whenever multi_tf_engine produces a conviction signal.
    First expires any open signals on the same timeframe.
    Returns the new signal_id or None if no conviction signal.
    """
    direction  = multi_tf_result.get("best_direction")
    tf         = multi_tf_result.get("best_timeframe")
    conviction = multi_tf_result.get("conviction")

    if not direction or not tf or not conviction:
        return None

    sb = get_supabase()

    # Expire any open signals on this timeframe
    try:
        open_signals = sb.table("signal_history")\
            .select("id, direction, entry_price, stop_loss, tp1_price")\
            .eq("status", "OPEN")\
            .eq("timeframe", tf)\
            .execute()

        for s in (open_signals.data or []):
            # Calculate outcome of expired signal
            current_price = multi_tf_result.get("entry_price", 0)
            pnl_pts = 0
            if s["direction"] == "long" and current_price:
                pnl_pts = round(current_price - float(s["entry_price"]), 2)
            elif s["direction"] == "short" and current_price:
                pnl_pts = round(float(s["entry_price"]) - current_price, 2)

            sb.table("signal_history").update({
                "status":         "EXPIRED",
                "expired":        True,
                "closed_time":    datetime.now(timezone.utc).isoformat(),
                "realized_pnl_pts": pnl_pts,
                "result_label":   "EXPIRED_PROFIT" if pnl_pts > 0 else "EXPIRED_LOSS",
            }).eq("id", s["id"]).execute()

    except Exception as e:
        logger.warning(f"Could not expire old signals: {e}")

    # Record the new signal
    signal_id = generate_signal_id(direction, tf)
    tps = multi_tf_result.get("take_profits", {})

    record = {
        "signal_id":      signal_id,
        "timeframe":      tf,
        "direction":      direction,
        "conviction":     conviction,
        "edge_strength":  multi_tf_result.get("edge_strength"),
        "entry_price":    multi_tf_result.get("entry_price"),
        "entry_time":     datetime.now(timezone.utc).isoformat(),
        "atr":            multi_tf_result.get("atr"),
        "risk_pct":       multi_tf_result.get("risk_pct"),
        "risk_usd":       multi_tf_result.get("risk_usd"),
        "risk_distance":  multi_tf_result.get("risk_distance"),
        "long_score":     multi_tf_result.get("long_score"),
        "short_score":    multi_tf_result.get("short_score"),
        "stop_loss":      multi_tf_result.get("stop_loss"),
        "tp1_price":      tps.get("tp1", {}).get("price"),
        "tp2_price":      tps.get("tp2", {}).get("price"),
        "tp3_price":      tps.get("tp3", {}).get("price"),
        "tp1_reward_usd": tps.get("tp1", {}).get("reward_usd"),
        "tp2_reward_usd": tps.get("tp2", {}).get("reward_usd"),
        "tp3_reward_usd": tps.get("tp3", {}).get("reward_usd"),
        "max_price":      multi_tf_result.get("entry_price"),
        "min_price":      multi_tf_result.get("entry_price"),
        "status":         "OPEN",
        "conditions_snapshot": multi_tf_result.get("timeframes", {}).get(tf, {}),
    }

    try:
        sb.table("signal_history").insert(record).execute()
        logger.info(f"Signal recorded: {signal_id} | {direction.upper()} {tf} @ ${record['entry_price']}")
        return signal_id
    except Exception as e:
        logger.error(f"Failed to record signal: {e}")
        return None


async def update_open_signals(current_price: float):
    """
    Called on every price update (every tick / scheduler poll).
    Checks all open signals and updates their status.
    """
    if not current_price or current_price <= 0:
        return

    sb = get_supabase()

    try:
        open_signals = sb.table("signal_history")\
            .select("*")\
            .eq("status", "OPEN")\
            .execute()
    except Exception as e:
        logger.error(f"Failed to fetch open signals: {e}")
        return

    for signal in (open_signals.data or []):
        try:
            await _check_and_update_signal(signal, current_price, sb)
        except Exception as e:
            logger.error(f"Error updating signal {signal.get('signal_id')}: {e}")


async def _check_and_update_signal(signal: dict, price: float, sb):
    """Check one signal against current price and update DB if anything hit."""
    sid       = signal["id"]
    direction = signal["direction"]
    entry     = float(signal["entry_price"] or 0)
    sl        = float(signal["stop_loss"] or 0)
    tp1       = float(signal["tp1_price"] or 0)
    tp2       = float(signal["tp2_price"] or 0)
    tp3       = float(signal["tp3_price"] or 0)

    updates   = {}
    now       = datetime.now(timezone.utc).isoformat()

    # Update price extremes
    cur_max = float(signal.get("max_price") or entry)
    cur_min = float(signal.get("min_price") or entry)
    if price > cur_max:
        updates["max_price"] = price
    if price < cur_min:
        updates["min_price"] = price

    # MAE/MFE
    if direction == "long":
        mfe = round(max(price, cur_max) - entry, 2)
        mae = round(entry - min(price, cur_min), 2)
    else:
        mfe = round(entry - min(price, cur_min), 2)
        mae = round(max(price, cur_max) - entry, 2)
    updates["max_favorable_excursion"] = max(mfe, float(signal.get("max_favorable_excursion") or 0))
    updates["max_adverse_excursion"]   = max(mae, float(signal.get("max_adverse_excursion") or 0))

    # Check targets and stop
    if direction == "long":
        # Stop loss hit
        if sl and price <= sl and not signal.get("stopped_out"):
            pnl = round(sl - entry, 2)
            updates.update({
                "stopped_out": True,
                "stop_hit_time": now,
                "status": "CLOSED",
                "closed_time": now,
                "realized_pnl_pts": pnl,
                "realized_pnl_usd": round(pnl * float(signal.get("risk_usd", 0) or 0) /
                                    max(float(signal.get("risk_distance", 1) or 1), 0.01), 2),
                "result_label": "STOPPED",
            })

        # TP1
        elif tp1 and price >= tp1 and not signal.get("tp1_hit"):
            updates["tp1_hit"] = True
            updates["tp1_hit_time"] = now
            updates["status"] = "TP1_HIT"
            logger.info(f"TP1 HIT: {signal['signal_id']} @ ${price}")

        # TP2 (only after TP1)
        if tp2 and price >= tp2 and signal.get("tp1_hit") and not signal.get("tp2_hit"):
            updates["tp2_hit"] = True
            updates["tp2_hit_time"] = now
            updates["status"] = "TP2_HIT"
            logger.info(f"TP2 HIT: {signal['signal_id']} @ ${price}")

        # TP3 (closes signal)
        if tp3 and price >= tp3 and signal.get("tp2_hit") and not signal.get("tp3_hit"):
            pnl = round(tp3 - entry, 2)
            updates.update({
                "tp3_hit": True,
                "tp3_hit_time": now,
                "status": "CLOSED",
                "closed_time": now,
                "realized_pnl_pts": pnl,
                "result_label": "TP3",
            })
            logger.info(f"TP3 HIT (FULL): {signal['signal_id']} @ ${price}")

    else:  # short
        if sl and price >= sl and not signal.get("stopped_out"):
            pnl = round(entry - sl, 2)
            updates.update({
                "stopped_out": True,
                "stop_hit_time": now,
                "status": "CLOSED",
                "closed_time": now,
                "realized_pnl_pts": -pnl,
                "result_label": "STOPPED",
            })

        elif tp1 and price <= tp1 and not signal.get("tp1_hit"):
            updates["tp1_hit"] = True
            updates["tp1_hit_time"] = now
            updates["status"] = "TP1_HIT"

        if tp2 and price <= tp2 and signal.get("tp1_hit") and not signal.get("tp2_hit"):
            updates["tp2_hit"] = True
            updates["tp2_hit_time"] = now
            updates["status"] = "TP2_HIT"

        if tp3 and price <= tp3 and signal.get("tp2_hit") and not signal.get("tp3_hit"):
            pnl = round(entry - tp3, 2)
            updates.update({
                "tp3_hit": True,
                "tp3_hit_time": now,
                "status": "CLOSED",
                "closed_time": now,
                "realized_pnl_pts": pnl,
                "result_label": "TP3",
            })

    if updates:
        sb.table("signal_history").update(updates).eq("id", sid).execute()


async def get_signal_history(limit: int = 100, timeframe: str | None = None) -> list:
    sb = get_supabase()
    query = sb.table("signal_history")\
        .select("*")\
        .order("entry_time", desc=True)\
        .limit(limit)
    if timeframe:
        query = query.eq("timeframe", timeframe)
    result = query.execute()
    return result.data or []


async def get_performance_stats() -> dict:
    """Summary stats for the track record dashboard."""
    sb    = get_supabase()
    data  = sb.table("signal_history").select("*")\
        .neq("status", "OPEN").execute().data or []

    if not data:
        return {"total": 0}

    total    = len(data)
    wins     = [s for s in data if s.get("result_label") in ["TP1","TP2","TP3","EXPIRED_PROFIT"]]
    losses   = [s for s in data if s.get("result_label") in ["STOPPED","EXPIRED_LOSS"]]
    tp1_hits = sum(1 for s in data if s.get("tp1_hit"))
    tp2_hits = sum(1 for s in data if s.get("tp2_hit"))
    tp3_hits = sum(1 for s in data if s.get("tp3_hit"))

    total_pnl = sum(float(s.get("realized_pnl_pts") or 0) for s in data)
    avg_win   = sum(float(s.get("realized_pnl_pts") or 0) for s in wins)   / len(wins)   if wins   else 0
    avg_loss  = sum(float(s.get("realized_pnl_pts") or 0) for s in losses) / len(losses) if losses else 0

    by_tf = {}
    for tf in ["15min","1h","4h"]:
        tf_signals = [s for s in data if s.get("timeframe") == tf]
        tf_wins    = [s for s in tf_signals if s.get("result_label") in ["TP1","TP2","TP3","EXPIRED_PROFIT"]]
        by_tf[tf]  = {
            "total":   len(tf_signals),
            "wins":    len(tf_wins),
            "win_pct": round(len(tf_wins) / len(tf_signals) * 100, 1) if tf_signals else 0,
        }

    return {
        "total":       total,
        "wins":        len(wins),
        "losses":      len(losses),
        "win_pct":     round(len(wins) / total * 100, 1) if total else 0,
        "tp1_hit_pct": round(tp1_hits / total * 100, 1) if total else 0,
        "tp2_hit_pct": round(tp2_hits / total * 100, 1) if total else 0,
        "tp3_hit_pct": round(tp3_hits / total * 100, 1) if total else 0,
        "total_pnl_pts": round(total_pnl, 2),
        "avg_win_pts": round(avg_win, 2),
        "avg_loss_pts": round(avg_loss, 2),
        "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 999,
        "by_timeframe": by_tf,
    }
