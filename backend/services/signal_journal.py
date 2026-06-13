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
        "fusion_assessment": multi_tf_result.get("technical_fusion"),
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
    """
    Check one signal against current price and update DB with proper
    R-multiple partial-close accounting.

    Model: 50% closes at TP1 / 25% at TP2 / 25% at TP3 (trailed). Once TP1
    hits, the stop moves to breakeven on the remaining position — so a
    stop-out after TP1 is never a full loss; it locks in the realized R from
    the TP1 portion and breaks even on the rest.

    realized_r is blended: 0.50R from TP1 + 0.25*2R from TP2 + 0.25*3R from TP3,
    or -1.0R on a full stop with no TPs hit, or partial-R + 0 on a
    breakeven-stop-after-TP1 close.
    """
    sid       = signal["id"]
    direction = signal["direction"]
    entry     = float(signal["entry_price"] or 0)
    orig_stop = float(signal["stop_loss"] or 0)
    tp1, tp2, tp3 = (float(signal.get(k) or 0) for k in ("tp1_price", "tp2_price", "tp3_price"))
    risk_dist = abs(entry - orig_stop) or 1.0
    now       = datetime.now(timezone.utc).isoformat()
    updates: dict = {}
    long      = direction == "long"

    def hit(target, is_long):
        return price >= target if is_long else price <= target

    # Effective stop: breakeven once TP1 has been hit
    stop_now      = entry if signal.get("tp1_hit") else orig_stop
    stop_breached = (price <= stop_now) if long else (price >= stop_now)

    # Portions: 50% at TP1, 25% at TP2, 25% at TP3
    tp1_hit = bool(signal.get("tp1_hit")) or (tp1 and hit(tp1, long))
    tp2_hit = bool(signal.get("tp2_hit")) or (tp1_hit and tp2 and hit(tp2, long))
    tp3_hit = bool(signal.get("tp3_hit")) or (tp2_hit and tp3 and hit(tp3, long))

    # Record newly-hit TPs
    if tp1_hit and not signal.get("tp1_hit"):
        updates.update({"tp1_hit": True, "tp1_hit_time": now,
                        "stop_moved_to_be": True, "status": "TP1_HIT"})
        logger.info(f"TP1 HIT: {signal['signal_id']} @ ${price} — stop moved to breakeven")
    if tp2_hit and not signal.get("tp2_hit"):
        updates.update({"tp2_hit": True, "tp2_hit_time": now, "status": "TP2_HIT"})
        logger.info(f"TP2 HIT: {signal['signal_id']} @ ${price}")
    if tp3_hit and not signal.get("tp3_hit"):
        updates.update({"tp3_hit": True, "tp3_hit_time": now})
        logger.info(f"TP3 HIT (FULL): {signal['signal_id']} @ ${price}")

    # Determine if the trade is now fully closed and compute blended R
    closed       = False
    outcome      = None
    result_label = None
    realized_r   = 0.0
    if tp1_hit: realized_r += 0.50 * 1.0
    if tp2_hit: realized_r += 0.25 * 2.0
    if tp3_hit: realized_r += 0.25 * 3.0

    if tp3_hit:
        closed       = True
        outcome      = "WIN"
        result_label = "TP3"
    elif stop_breached and not signal.get("stopped_out"):
        closed      = True
        closed_frac = (0.50 if tp1_hit else 0) + (0.25 if tp2_hit else 0)
        remaining   = 1.0 - closed_frac
        if signal.get("tp1_hit") or tp1_hit:
            realized_r  += remaining * 0.0          # breakeven stop on remainder
            outcome      = "WIN" if realized_r > 0.01 else "BREAKEVEN"
            result_label = "STOPPED_BE_AFTER_TP"
        else:
            realized_r   = -1.0                      # full stop, no TP hit
            outcome      = "LOSS"
            result_label = "STOPPED"

    if closed:
        realized_pts = round(realized_r * risk_dist, 2)
        risk_usd     = float(signal.get("risk_usd") or 0)
        updates.update({
            "stopped_out":      stop_breached,
            "stop_hit_time":    now if stop_breached else signal.get("stop_hit_time"),
            "status":           "CLOSED",
            "closed_time":      now,
            "realized_r":       round(realized_r, 3),
            "realized_pnl_pts": realized_pts,
            "realized_pnl_usd": round(realized_r * risk_usd, 2),
            "result_label":     result_label,
            "outcome_class":    outcome,
            "portions_closed": {
                "tp1": 0.50 if tp1_hit else 0,
                "tp2": 0.25 if tp2_hit else 0,
                "tp3": 0.25 if tp3_hit else 0,
            },
        })

    # Update price extremes
    cur_max = float(signal.get("max_price") or entry)
    cur_min = float(signal.get("min_price") or entry)
    if price > cur_max:
        updates["max_price"] = price
    if price < cur_min:
        updates["min_price"] = price

    # Track MAE/MFE for trade-quality analysis
    mfe = (price - entry) if long else (entry - price)
    mae = (entry - price) if long else (price - entry)
    updates["max_favorable_excursion"] = round(max(mfe, float(signal.get("max_favorable_excursion") or 0)), 2)
    updates["max_adverse_excursion"]   = round(max(mae, float(signal.get("max_adverse_excursion") or 0)), 2)

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

    # Prefer the new outcome_class (set by the R-multiple accounting in
    # _check_and_update_signal); fall back to the legacy result_label for
    # rows recorded before this migration so historical stats don't vanish.
    def _outcome(s):
        oc = s.get("outcome_class")
        if oc:
            return oc
        rl = s.get("result_label")
        if rl in ("TP1", "TP2", "TP3", "EXPIRED_PROFIT"):
            return "WIN"
        if rl in ("STOPPED", "EXPIRED_LOSS"):
            return "LOSS"
        return None

    wins       = [s for s in data if _outcome(s) == "WIN"]
    losses     = [s for s in data if _outcome(s) == "LOSS"]
    breakevens = [s for s in data if _outcome(s) == "BREAKEVEN"]
    closed     = wins + losses + breakevens

    tp1_hits = sum(1 for s in data if s.get("tp1_hit"))
    tp2_hits = sum(1 for s in data if s.get("tp2_hit"))
    tp3_hits = sum(1 for s in data if s.get("tp3_hit"))

    def _r(s):
        r = s.get("realized_r")
        return float(r) if r is not None else 0.0

    r_values   = [_r(s) for s in closed if s.get("realized_r") is not None]
    avg_r      = round(sum(r_values) / len(r_values), 3) if r_values else 0.0
    pos_r      = [r for r in r_values if r > 0]
    neg_r      = [r for r in r_values if r < 0]
    profit_factor_r = round(sum(pos_r) / abs(sum(neg_r)), 2) if neg_r else (999 if pos_r else 0)

    total_pnl = sum(float(s.get("realized_pnl_pts") or 0) for s in data)
    avg_win   = sum(float(s.get("realized_pnl_pts") or 0) for s in wins)   / len(wins)   if wins   else 0
    avg_loss  = sum(float(s.get("realized_pnl_pts") or 0) for s in losses) / len(losses) if losses else 0

    by_tf = {}
    for tf in ["15min", "1h", "4h"]:
        tf_signals   = [s for s in data   if s.get("timeframe") == tf]
        tf_closed    = [s for s in closed if s.get("timeframe") == tf]
        tf_wins      = [s for s in tf_closed if _outcome(s) == "WIN"]
        tf_losses    = [s for s in tf_closed if _outcome(s) == "LOSS"]
        tf_be        = [s for s in tf_closed if _outcome(s) == "BREAKEVEN"]
        tf_r         = [_r(s) for s in tf_closed if s.get("realized_r") is not None]
        by_tf[tf] = {
            "total":      len(tf_signals),
            "closed":     len(tf_closed),
            "wins":       len(tf_wins),
            "losses":     len(tf_losses),
            "breakevens": len(tf_be),
            "win_pct":    round(len(tf_wins) / len(tf_closed) * 100, 1) if tf_closed else 0,
            "avg_r":      round(sum(tf_r) / len(tf_r), 3) if tf_r else 0.0,
            "expectancy": round(sum(tf_r) / len(tf_r), 3) if tf_r else 0.0,
        }

    return {
        "total":          total,
        "closed":         len(closed),
        "wins":           len(wins),
        "losses":         len(losses),
        "breakevens":     len(breakevens),
        "win_pct":        round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "tp1_hit_pct":    round(tp1_hits / total * 100, 1) if total else 0,
        "tp2_hit_pct":    round(tp2_hits / total * 100, 1) if total else 0,
        "tp3_hit_pct":    round(tp3_hits / total * 100, 1) if total else 0,
        # R-multiple metrics — the honest measure of whether this system
        # makes money. avg_R == expectancy: positive means net profitable
        # over time at constant risk-per-trade.
        "avg_r":          avg_r,
        "expectancy":     avg_r,
        "profit_factor_r": profit_factor_r,
        # Legacy point-based metrics retained for backward compatibility
        "total_pnl_pts":  round(total_pnl, 2),
        "avg_win_pts":    round(avg_win, 2),
        "avg_loss_pts":   round(avg_loss, 2),
        "profit_factor":  round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 999,
        "by_timeframe":   by_tf,
    }


async def get_equity_curve(starting_capital: float = 10000.0, timeframe: str | None = None) -> dict:
    """Chronological equity curve from realized_pnl_usd + monthly P&L breakdown."""
    sb = get_supabase()
    query = sb.table("signal_history").select("*").neq("status", "OPEN").order("closed_time")
    if timeframe:
        query = query.eq("timeframe", timeframe)
    data = query.execute().data or []

    points = []
    equity  = starting_capital
    cum_pts = 0.0
    peak    = starting_capital
    max_dd  = 0.0
    monthly: dict = {}

    for s in data:
        if not s.get("closed_time"):
            continue
        pnl_usd = float(s.get("realized_pnl_usd") or 0)
        pnl_pts = float(s.get("realized_pnl_pts") or 0)
        equity  += pnl_usd
        cum_pts += pnl_pts
        peak     = max(peak, equity)
        dd       = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd   = max(max_dd, dd)

        points.append({
            "signal_id":    s.get("signal_id"),
            "closed_time":  s.get("closed_time"),
            "timeframe":    s.get("timeframe"),
            "pnl_usd":      round(pnl_usd, 2),
            "pnl_pts":      round(pnl_pts, 2),
            "equity":       round(equity, 2),
            "cum_pts":      round(cum_pts, 2),
            "drawdown_pct": round(dd, 2),
        })

        month_key = s["closed_time"][:7]
        m = monthly.setdefault(month_key, {"month": month_key, "pnl_usd": 0.0, "trades": 0, "wins": 0})
        m["pnl_usd"] += pnl_usd
        m["trades"]  += 1
        if (s.get("outcome_class") == "WIN") or (float(s.get("realized_r") or 0) > 0):
            m["wins"] += 1

    monthly_list = []
    for m in sorted(monthly.values(), key=lambda x: x["month"]):
        m["pnl_usd"] = round(m["pnl_usd"], 2)
        m["win_pct"] = round(m["wins"] / m["trades"] * 100, 1) if m["trades"] else 0
        monthly_list.append(m)

    return {
        "starting_capital": starting_capital,
        "final_equity":     round(equity, 2),
        "final_cum_pts":    round(cum_pts, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "points":           points,
        "monthly":          monthly_list,
    }


async def get_condition_stats(timeframe: str | None = None) -> list:
    """Win rate / avg R per (condition, value) from conditions_snapshot JSON."""
    from collections import defaultdict
    sb = get_supabase()
    query = sb.table("signal_history").select(
        "direction, outcome_class, realized_r, realized_pnl_pts, conditions_snapshot"
    ).neq("status", "OPEN")
    if timeframe:
        query = query.eq("timeframe", timeframe)
    data = query.execute().data or []

    stats: dict = defaultdict(lambda: {"total": 0, "wins": 0, "sum_r": 0.0, "sum_pnl": 0.0})

    for s in data:
        snap       = s.get("conditions_snapshot") or {}
        conditions = snap.get("conditions") or {}
        if not conditions:
            continue
        direction = s.get("direction")
        is_win    = (s.get("outcome_class") == "WIN") or (float(s.get("realized_r") or 0) > 0)
        r_val     = float(s.get("realized_r") or 0)
        pnl_val   = float(s.get("realized_pnl_pts") or 0)

        for cond_name, cond in conditions.items():
            met = cond.get("long_met") if direction == "long" else cond.get("short_met")
            if not met:
                continue
            key = (cond_name, str(cond.get("value", "")))
            st = stats[key]
            st["total"]   += 1
            st["wins"]    += 1 if is_win else 0
            st["sum_r"]   += r_val
            st["sum_pnl"] += pnl_val

    result = []
    for (cond_name, value), st in stats.items():
        if st["total"] == 0:
            continue
        result.append({
            "condition":   cond_name,
            "value":       value,
            "signals":     st["total"],
            "win_pct":     round(st["wins"] / st["total"] * 100, 1),
            "avg_r":       round(st["sum_r"] / st["total"], 3),
            "avg_pnl_pts": round(st["sum_pnl"] / st["total"], 2),
        })

    result.sort(key=lambda x: x["avg_r"], reverse=True)
    return result
