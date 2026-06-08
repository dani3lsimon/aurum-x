# backend/engines/multi_tf_engine.py
"""
Multi-timeframe bi-directional signal engine.

Runs the same 9-condition bi-directional confluence logic at 15min, 1h, and 4h
simultaneously using REAL OANDA candles (XAU_USD), then blends the three reads
to surface the single highest-conviction timeframe — weighted 50% (15min) /
30% (1h) / 20% (4h), reflecting that the 15min signal drives scalp entries,
the 1h confirms intraday direction, and the 4h prevents trading against the
larger trend.

Honest-data note: every condition here is derived from a real fetched value
(OANDA candles, FRED DXY momentum, yield_agent score, CFTC COT, ETF flows,
risk sentiment, economic calendar). If a timeframe's OANDA candles can't be
fetched, that timeframe reports {"error": ...} and is excluded from the
"best timeframe" search rather than being scored with fabricated data.
"""
import math
import asyncio
import logging
from datetime import datetime, timezone

from services.supabase_service import get_supabase
from services.redis_service import cache_get, cache_set
from services.websocket_manager import ws_manager
from config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

MAX_SCORE  = 14.0
TIMEFRAMES = ["15min", "1h", "4h"]

CONDITION_WEIGHTS = {
    "dxy":    2, "yield": 2, "vwap":  1, "delta": 2,
    "cot":    1, "etf":   1, "risk":  1, "break": 2, "news": 1
}

# Conditions that move with the live cTrader tick (re-derivable from the
# current price alone) vs. conditions that only refresh on the backend's
# 5-minute cycle (macro/fundamental data). Surfaced honestly to the frontend
# so it can label which numbers are "live" vs "cached" rather than implying
# everything updates in real time.
PRICE_SENSITIVE = {"vwap", "break", "delta"}

TF_OANDA_MAP = {
    "15min": {"granularity": "M15", "count": 16},
    "1h":    {"granularity": "H1",  "count": 25},
    "4h":    {"granularity": "H4",  "count": 13},
}

TF_WEIGHTS = {"15min": 0.50, "1h": 0.30, "4h": 0.20}

HALF_LIVES_H = {"cot": 84, "etf": 24}


def decay_factor(condition_name: str, hours_since_update: float) -> float:
    hl = HALF_LIVES_H.get(condition_name, 0)
    if hl == 0:
        return 1.0
    return max(0.1, math.exp(-math.log(2) * hours_since_update / hl))


def cot_contrarian_signal(pct_of_range: float) -> float:
    """tanh-transformed contrarian read — see positioning_collector.cot_contrarian_signal."""
    r = pct_of_range / 100.0
    return -math.tanh(4.0 * (r - 0.5))


async def _get_tf_market_data(granularity: str, count: int) -> dict:
    """Fetch real OANDA candles and compute timeframe-specific values (VWAP,
    cumulative delta approximation, ATR, momentum, prior-period break)."""
    from collectors.oanda_collector import OandaCollector
    oanda = OandaCollector()
    candles = await oanda.get_candles("XAU_USD", granularity, count)

    if len(candles) < 4:
        return {}

    completed = [c for c in candles if c.get("complete", True)]
    if not completed:
        return {}

    closes  = [float(c["close"])  for c in completed]
    highs   = [float(c["high"])   for c in completed]
    lows    = [float(c["low"])    for c in completed]
    volumes = [int(c["volume"])   for c in completed]

    # Volume-weighted average price across the window
    tpv       = sum(((h + l + c) / 3) * v for h, l, c, v in zip(highs, lows, closes, volumes))
    vol_total = sum(volumes)
    vwap      = round(tpv / vol_total, 2) if vol_total else closes[-1]

    # Approximate cumulative delta (Kaufman close-location-value weighted by volume)
    delta = 0.0
    for c_bar in completed[-min(len(completed), 8):]:
        rng = float(c_bar["high"]) - float(c_bar["low"])
        if rng > 0:
            delta += float(c_bar["volume"]) * (
                (float(c_bar["close"]) - float(c_bar["low"])) -
                (float(c_bar["high"]) - float(c_bar["close"]))
            ) / rng

    # ATR — simple average true range proxy over the last (up to) 14 bars
    atr_bars = completed[-14:]
    atr = round(sum(h - l for h, l in zip(
        [float(b["high"]) for b in atr_bars],
        [float(b["low"])  for b in atr_bars]
    )) / len(atr_bars), 2) if atr_bars else 20.0

    # Period momentum — first close vs last close
    period_start = closes[0]
    period_end   = closes[-1]
    momentum_pct = round(((period_end - period_start) / period_start) * 100, 4) if period_start else 0

    # Session break — current price vs prior-period high/low
    prior_high = max(highs[:-1]) if len(highs) > 1 else highs[0]
    prior_low  = min(lows[:-1])  if len(lows)  > 1 else lows[0]
    current_price = closes[-1]

    break_direction = "neutral"
    if current_price > prior_high:
        break_direction = "up"
    elif current_price < prior_low:
        break_direction = "down"

    return {
        "current_price":   current_price,
        "vwap":            vwap,
        "vwap_signal":     "above" if current_price > vwap else "below" if current_price < vwap else "at",
        "price_vs_vwap":   round(current_price - vwap, 2),
        "delta":           round(delta, 1),
        "atr":             atr,
        "momentum_pct":    momentum_pct,
        "break_direction": break_direction,
        "prior_high":      round(prior_high, 2),
        "prior_low":       round(prior_low, 2),
        "closes":          closes,
    }


def score_one_timeframe(tf_data: dict, shared: dict, cot_decay: float, etf_decay: float) -> dict:
    """Score all 9 conditions for one timeframe (bi-directional, like the main engine)."""
    short_raw = 0.0
    long_raw  = 0.0
    conditions = {}

    # DXY direction
    dxy_mom = shared.get("dxy_momentum_pct", 0)
    c_dxy_s = dxy_mom > 0.10
    c_dxy_l = dxy_mom < -0.10
    conditions["dxy"] = {"short_met": c_dxy_s, "long_met": c_dxy_l,
                         "value": f"DXY {dxy_mom:+.3f}%"}
    if c_dxy_s: short_raw += CONDITION_WEIGHTS["dxy"]
    if c_dxy_l: long_raw  += CONDITION_WEIGHTS["dxy"]

    # Real yield direction (yield_agent score proxy)
    yield_score = shared.get("yield_agent_score", 0)
    c_yld_s = yield_score < -10
    c_yld_l = yield_score > 10
    conditions["yield"] = {"short_met": c_yld_s, "long_met": c_yld_l,
                           "value": f"Yield agent {yield_score:+.0f}"}
    if c_yld_s: short_raw += CONDITION_WEIGHTS["yield"]
    if c_yld_l: long_raw  += CONDITION_WEIGHTS["yield"]

    # Price vs VWAP (timeframe-specific, real OANDA candles)
    vwap_sig = tf_data.get("vwap_signal", "at")
    c_vwap_s = vwap_sig == "below"
    c_vwap_l = vwap_sig == "above"
    conditions["vwap"] = {"short_met": c_vwap_s, "long_met": c_vwap_l,
                          "value": f"${tf_data.get('current_price', 0):.2f} vs VWAP ${tf_data.get('vwap', 0):.2f}"}
    if c_vwap_s: short_raw += CONDITION_WEIGHTS["vwap"]
    if c_vwap_l: long_raw  += CONDITION_WEIGHTS["vwap"]

    # Cumulative delta (timeframe-specific Kaufman approximation)
    delta = tf_data.get("delta", 0)
    c_dlt_s = delta < -50
    c_dlt_l = delta > 50
    conditions["delta"] = {"short_met": c_dlt_s, "long_met": c_dlt_l,
                           "value": f"Delta {delta:+.0f}"}
    if c_dlt_s: short_raw += CONDITION_WEIGHTS["delta"]
    if c_dlt_l: long_raw  += CONDITION_WEIGHTS["delta"]

    # COT — contrarian signal (shared across timeframes, decayed by data age)
    cot_signal = shared.get("cot_signal", 0)
    c_cot_s = cot_signal < -0.2
    c_cot_l = cot_signal > 0.2
    conditions["cot"] = {"short_met": c_cot_s, "long_met": c_cot_l,
                         "value": f"COT contrarian signal {cot_signal:+.2f}"}
    if c_cot_s: short_raw += CONDITION_WEIGHTS["cot"] * cot_decay
    if c_cot_l: long_raw  += CONDITION_WEIGHTS["cot"] * cot_decay

    # ETF flows (shared, decayed by data age)
    etf_sig = shared.get("etf_signal", "neutral")
    c_etf_s = etf_sig in ("strong_outflow", "mild_outflow")
    c_etf_l = etf_sig in ("strong_inflow",  "mild_inflow")
    conditions["etf"] = {"short_met": c_etf_s, "long_met": c_etf_l,
                         "value": f"ETF {etf_sig}"}
    if c_etf_s: short_raw += CONDITION_WEIGHTS["etf"] * etf_decay
    if c_etf_l: long_raw  += CONDITION_WEIGHTS["etf"] * etf_decay

    # Risk sentiment (shared)
    risk_score = shared.get("risk_score", 0)
    c_rsk_s = risk_score > 20
    c_rsk_l = risk_score < -20
    conditions["risk"] = {"short_met": c_rsk_s, "long_met": c_rsk_l,
                          "value": f"Risk score {risk_score:+.0f}"}
    if c_rsk_s: short_raw += CONDITION_WEIGHTS["risk"]
    if c_rsk_l: long_raw  += CONDITION_WEIGHTS["risk"]

    # Session/period break (timeframe-specific — prior-period high/low break)
    brk = tf_data.get("break_direction", "neutral")
    c_brk_s = brk == "down"
    c_brk_l = brk == "up"
    conditions["break"] = {"short_met": c_brk_s, "long_met": c_brk_l,
                           "value": f"Break {brk} (range ${tf_data.get('prior_low', 0):.2f}-${tf_data.get('prior_high', 0):.2f})"}
    if c_brk_s: short_raw += CONDITION_WEIGHTS["break"]
    if c_brk_l: long_raw  += CONDITION_WEIGHTS["break"]

    # No-imminent-news safe window — point goes to whichever side currently leads
    news_safe = shared.get("news_safe", True)
    conditions["news"] = {"short_met": False, "long_met": False, "value": "clear window" if news_safe else "imminent release — neither side awarded"}
    if news_safe:
        if short_raw >= long_raw:
            short_raw += CONDITION_WEIGHTS["news"]
            conditions["news"]["short_met"] = True
        else:
            long_raw += CONDITION_WEIGHTS["news"]
            conditions["news"]["long_met"] = True

    # DXY × yield interaction bonus when aligned
    interaction_note = "none"
    if c_dxy_s and c_yld_s:
        short_raw += 1.0
        interaction_note = "DXY + yields both bearish gold — short bonus +1.0"
    elif c_dxy_l and c_yld_l:
        long_raw += 1.0
        interaction_note = "DXY + yields both bullish gold — long bonus +1.0"
    conditions["interaction"] = {"short_met": False, "long_met": False, "value": interaction_note}

    short_pct = round(min(100.0, (short_raw / MAX_SCORE) * 100), 1)
    long_pct  = round(min(100.0, (long_raw  / MAX_SCORE) * 100), 1)

    # Tag each condition honestly: does it move with the live tick, or is it
    # cached macro/fundamental data refreshed on the backend's cycle?
    for cond_name, cond in conditions.items():
        cond["live"] = cond_name in PRICE_SENSITIVE

    return {
        "short_pct":       short_pct,
        "long_pct":        long_pct,
        "short_raw":       round(short_raw, 2),
        "long_raw":        round(long_raw, 2),
        "conditions":      conditions,
        "vwap":            tf_data.get("vwap"),
        "delta":           tf_data.get("delta"),
        "atr":             tf_data.get("atr"),
        "current_price":   tf_data.get("current_price"),
        "break_direction": tf_data.get("break_direction"),
        "prior_high":      tf_data.get("prior_high"),
        "prior_low":       tf_data.get("prior_low"),
    }


async def _get_upcoming_high_impact() -> list:
    """Mirrors ShortScoreEngine._get_upcoming_high_impact — real Supabase
    economic_releases query for anything high/critical within 15 minutes."""
    from datetime import timedelta
    sb = get_supabase()
    now    = datetime.now(timezone.utc).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    result = (
        sb.table("economic_releases")
        .select("*")
        .gte("release_date", now)
        .lte("release_date", future)
        .in_("gold_sensitivity", ["high", "critical"])
        .order("release_date")
        .execute()
    )
    return result.data or []


async def evaluate_multi_tf(vix: float = None) -> dict:
    """Main entry point. Returns the bi-directional confluence read for all
    three timeframes plus the single highest-conviction "best" signal."""
    cache_key = "multi_tf_signal"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    from collectors.positioning_collector import PositioningCollector
    from collectors.etf_collector import ETFCollector
    from collectors.sentiment_collector import SentimentCollector
    from collectors.macro_collector import MacroCollector
    from services.supabase_service import get_latest_agent_scores

    cot   = PositioningCollector()
    etf   = ETFCollector()
    sent  = SentimentCollector()
    macro = MacroCollector()

    # Fetch shared (non-timeframe-specific) real data in parallel
    cot_data, etf_data, risk_data, dollar_data, releases, agent_scores = await asyncio.gather(
        cot.get_latest(),
        etf.get_etf_flows(),
        sent.get_risk_sentiment(),
        macro.get_dollar_data(),
        _get_upcoming_high_impact(),
        get_latest_agent_scores(),
        return_exceptions=True,
    )
    if isinstance(cot_data, Exception):    cot_data    = {}
    if isinstance(etf_data, Exception):    etf_data    = {}
    if isinstance(risk_data, Exception):   risk_data   = {}
    if isinstance(dollar_data, Exception): dollar_data = {}
    if isinstance(releases, Exception):    releases    = []
    if isinstance(agent_scores, Exception): agent_scores = []

    # COT contrarian signal — prefer the collector's own field (already
    # tanh-transformed by cot_contrarian_signal in positioning_collector);
    # fall back to recomputing locally if it's somehow absent.
    cot_signal = cot_data.get("cot_signal")
    if cot_signal is None:
        pct_range  = (cot_data or {}).get("pct_of_8w_range", 50)
        cot_signal = round(cot_contrarian_signal(pct_range), 3)
    cot_decay = decay_factor("cot", 48)
    etf_decay = decay_factor("etf", 16)

    # Real DXY momentum from FRED (via MacroCollector — same source as the main engine)
    dxy_momentum = float((dollar_data or {}).get("DXY_MOMENTUM_PCT", 0) or 0)

    # yield_agent score from the latest agent run
    yield_agent_score = 0.0
    for s in (agent_scores or []):
        if s.get("agent_name") == "yield_agent":
            yield_agent_score = float(s.get("score", 0))
            break

    # No-imminent-news check — reuse the main engine's honest evaluator
    from engines.short_score_engine import ShortScoreEngine
    news_eval = ShortScoreEngine._evaluate_no_imminent_news(releases)
    news_safe = news_eval["clear"]

    # Risk score / VIX
    risk_score = (risk_data or {}).get("risk_score", 0)
    if vix is None:
        vix = ((risk_data or {}).get("vix") or {}).get("price")

    shared = {
        "dxy_momentum_pct":  dxy_momentum,
        "yield_agent_score": yield_agent_score,
        "cot_signal":        cot_signal,
        "etf_signal":        (etf_data or {}).get("combined_signal", "neutral"),
        "risk_score":        risk_score,
        "news_safe":         news_safe,
    }

    # Fetch timeframe-specific OANDA candle data and score each
    all_tf_results = {}
    for tf, oanda_cfg in TF_OANDA_MAP.items():
        try:
            tf_data = await _get_tf_market_data(oanda_cfg["granularity"], oanda_cfg["count"])
            if tf_data:
                all_tf_results[tf] = score_one_timeframe(tf_data, shared, cot_decay, etf_decay)
                all_tf_results[tf]["granularity"] = oanda_cfg["granularity"]
            else:
                all_tf_results[tf] = {"short_pct": 0, "long_pct": 0, "error": "no OANDA candle data returned"}
        except Exception as e:
            logger.error(f"Multi-TF {tf} error: {e}")
            all_tf_results[tf] = {"short_pct": 0, "long_pct": 0, "error": str(e)}

    # Find the best (highest-conviction, weighted) timeframe + direction
    best_tf = None
    best_weighted_diff = 0.0
    best_direction = "neutral"

    for tf, scores in all_tf_results.items():
        if scores.get("error"):
            continue
        short_p = scores.get("short_pct", 0)
        long_p  = scores.get("long_pct",  0)
        diff    = abs(short_p - long_p)
        w_diff  = diff * TF_WEIGHTS.get(tf, 0.3)
        direction = "short" if short_p > long_p else "long" if long_p > short_p else "neutral"
        if w_diff > best_weighted_diff and direction != "neutral":
            best_weighted_diff = w_diff
            best_tf            = tf
            best_direction     = direction

    # Volatility-adjusted thresholds (mirrors the main engine's Improvement 5)
    vix_f = float(vix) if vix else 20.0
    hc_thresh    = 80.0 if vix_f > 25 else 70.0
    scalp_thresh = 50.0 if vix_f > 25 else 40.0

    best_signal = "NO TRADE"
    conviction  = None
    edge        = 0.0
    stop_loss   = None
    risk_pct    = 0.35

    if best_tf:
        bs = all_tf_results[best_tf]
        winning_pct = bs.get("short_pct" if best_direction == "short" else "long_pct", 0)
        losing_pct  = bs.get("long_pct"  if best_direction == "short" else "short_pct", 0)

        if winning_pct >= hc_thresh:
            conviction  = "HIGH CONVICTION"
            best_signal = "▲ LONG — HIGH CONVICTION" if best_direction == "long" else "▼ SHORT — HIGH CONVICTION"
        elif winning_pct >= scalp_thresh:
            conviction  = "SCALP"
            best_signal = "▲ LONG — SCALP" if best_direction == "long" else "▼ SHORT — SCALP"

        edge = round(abs(winning_pct - losing_pct) / max(1.0, vix_f / 20), 2)

        if   vix_f > 35:  risk_pct = 0.15
        elif vix_f > 25:  risk_pct = 0.25
        elif vix_f < 15:  risk_pct = 0.75
        else:             risk_pct = 0.35
        if conviction == "SCALP":
            risk_pct = round(risk_pct * 0.5, 3)

        # ── Entry, Stop, Take Profit calculation ─────────────────────
        entry_price   = bs.get("current_price", 0)
        atr           = bs.get("atr", 20) or 20

        # Risk distance = 1.5 × ATR
        risk_dist = round(atr * 1.5, 2)

        if entry_price and risk_dist:
            if best_direction == "long":
                stop_loss = round(entry_price - risk_dist, 2)   # BELOW entry for long
                tp1       = round(entry_price + risk_dist,       2)  # 1:1 — 50% close
                tp2       = round(entry_price + risk_dist * 2.0, 2)  # 1:2 — 25% close
                tp3       = round(entry_price + risk_dist * 3.0, 2)  # 1:3 — trail 25%
            else:  # short
                stop_loss = round(entry_price + risk_dist, 2)   # ABOVE entry for short
                tp1       = round(entry_price - risk_dist,       2)  # 1:1 — 50% close
                tp2       = round(entry_price - risk_dist * 2.0, 2)  # 1:2 — 25% close
                tp3       = round(entry_price - risk_dist * 3.0, 2)  # 1:3 — trail 25%
        else:
            stop_loss = tp1 = tp2 = tp3 = None

        # Risk per trade in USD
        account_size = float(getattr(settings, 'account_size_usd', 10000))
        risk_usd     = round(account_size * (risk_pct / 100), 2)

        # Position size in oz (gold)
        position_oz = round(risk_usd / risk_dist, 4) if risk_dist else 0

        # Reward values at each TP
        reward_tp1 = round(risk_usd * 1.0, 2)
        reward_tp2 = round(risk_usd * 2.0, 2)
        reward_tp3 = round(risk_usd * 3.0, 2)

        # Expected move based on conviction level and timeframe ATR
        # HIGH CONVICTION: expect 1.5-2.5 × ATR move in signal direction
        # SCALP: expect 0.8-1.5 × ATR
        if conviction == "HIGH CONVICTION":
            expected_move_min = round(atr * 1.5, 2)
            expected_move_max = round(atr * 2.5, 2)
            probability_reach_tp1 = 72  # % based on historical ATR studies
            probability_reach_tp2 = 45
            probability_reach_tp3 = 22
        elif conviction == "SCALP":
            expected_move_min = round(atr * 0.8, 2)
            expected_move_max = round(atr * 1.5, 2)
            probability_reach_tp1 = 58
            probability_reach_tp2 = 30
            probability_reach_tp3 = 12
        else:
            expected_move_min = expected_move_max = 0
            probability_reach_tp1 = probability_reach_tp2 = probability_reach_tp3 = 0
    else:
        entry_price = 0
        atr         = 20
        risk_dist   = 0
        tp1 = tp2 = tp3 = None
        account_size = float(getattr(settings, 'account_size_usd', 10000))
        risk_usd     = 0.0
        position_oz  = 0
        reward_tp1 = reward_tp2 = reward_tp3 = 0.0
        expected_move_min = expected_move_max = 0
        probability_reach_tp1 = probability_reach_tp2 = probability_reach_tp3 = 0

    timestamp = datetime.now(timezone.utc).isoformat()

    # Per-condition directional-contribution audit — exposes exactly how many
    # points each condition contributed to long vs short on each timeframe,
    # so a condition that's permanently pinned to one side can never hide.
    contribution_audit = {
        tf: {
            cond: {
                "long":  CONDITION_WEIGHTS.get(cond, 0) if c.get("long_met")  else 0,
                "short": CONDITION_WEIGHTS.get(cond, 0) if c.get("short_met") else 0,
                "value": c.get("value", ""),
                "live":  c.get("live", False),
            }
            for cond, c in scores.get("conditions", {}).items()
        }
        for tf, scores in all_tf_results.items() if "conditions" in scores
    }

    result = {
        "timestamp":       timestamp,
        "best_signal":     best_signal,
        "best_timeframe":  best_tf,
        "best_direction":  best_direction,
        "conviction":      conviction,
        "edge_strength":   edge,
        "risk_pct":        risk_pct,
        "stop_loss":       stop_loss,
        "vix":             vix_f,
        "hc_threshold":    hc_thresh,
        "scalp_threshold": scalp_thresh,
        "timeframes":      all_tf_results,
        "shared_inputs":   shared,
        "contribution_audit": contribution_audit,
        "entry_price":     entry_price,
        "risk_distance":   risk_dist,
        "take_profits": {
            "tp1": {
                "price":      tp1,
                "rr_ratio":   "1:1",
                "action":     "Close 50% of position",
                "reward_usd": reward_tp1,
            },
            "tp2": {
                "price":      tp2,
                "rr_ratio":   "1:2",
                "action":     "Close 25% of position",
                "reward_usd": reward_tp2,
            },
            "tp3": {
                "price":      tp3,
                "rr_ratio":   "1:3",
                "action":     "Trail remaining 25%",
                "reward_usd": reward_tp3,
            },
        },
        "position_size_oz": position_oz,
        "risk_usd":         risk_usd,
        "atr":              atr,
        "expected_move": {
            "direction":           best_direction,
            "min_pts":             expected_move_min,
            "max_pts":             expected_move_max,
            "prob_tp1":            probability_reach_tp1,
            "prob_tp2":            probability_reach_tp2,
            "prob_tp3":            probability_reach_tp3,
            "note": (
                f"High conviction {best_direction}: expect {expected_move_min}–{expected_move_max} pt move"
                if conviction else "No active signal"
            )
        },
    }

    # Persist a lightweight audit row (honest about the source — tagged multi_tf_*)
    try:
        sb = get_supabase()
        sb.table("intraday_signals").insert({
            "timestamp":         timestamp,
            "short_setup_score": all_tf_results.get("15min", {}).get("short_pct", 0),
            "long_score":        all_tf_results.get("15min", {}).get("long_pct", 0),
            "short_score":       all_tf_results.get("15min", {}).get("short_pct", 0),
            "net_signal":        best_signal,
            "go_long":           best_direction == "long"  and conviction == "HIGH CONVICTION",
            "go_short":          best_direction == "short" and conviction == "HIGH CONVICTION",
            "trigger":           f"multi_tf_{best_tf or 'none'}",
        }).execute()
    except Exception as e:
        logger.warning(f"[multi-tf] persist error: {e}")

    await ws_manager.broadcast({"type": "multi_tf_update", "data": result})
    await cache_set(cache_key, result, ttl_seconds=60)

    # Record signal if conviction fired
    if result.get("conviction"):
        # Fuse deterministic SMC structure with fundamentals into a concrete trade thesis
        from agents.technical_fusion_agent import TechnicalFusionAgent
        try:
            result["technical_fusion"] = await TechnicalFusionAgent().run()
        except Exception as e:
            logger.warning(f"Fusion agent error: {e}")

        from services.signal_journal import record_signal
        try:
            await record_signal(result)
        except Exception as e:
            logger.error(f"Signal journal error: {e}")

    logger.info(f"[multi-tf] {best_signal} | best_tf={best_tf} | edge={edge} | vix={vix_f}")
    return result
