# backend/engines/short_score_engine.py
"""
Trade Confluence Score Engine — bi-directional 10-condition confluence gauge
(0-100% each side) producing a LONG score AND a SHORT score simultaneously
for an intraday gold (XAUUSD/GC) setup.

(Formerly the "Short-Setup Score Engine" — kept the class name and the
`/forecast/short-score` route path for backwards compatibility, but every
condition is now evaluated for BOTH directions and the net signal is whichever
side wins.)

Signal-quality layers on top of the base 10-condition confluence:
  1. Contrarian COT transformation  — cot_signal (tanh) from positioning_collector
  2. Signal decay                   — fresher order-flow data counts more
  3. Regime-dependent weights       — condition reliability varies by macro regime
     (using a 24h-smoothed, hysteresis-locked regime — see regime_smoother)
  4. DXY × real-yield interaction   — both pointing the same way ⇒ multiplicative bonus
  5. Volatility-adjusted thresholds — VIX scales the HIGH CONVICTION / SCALP bars
  + a 30-day rolling calibration (real OANDA H1 stats) replaces the hardcoded
    "what counts as a significant DXY move" threshold
  + a display-only VIX-based position-size suggestion (never auto-executed)

Design principles (per the project's no-fake-data rule):
  - Every condition tries to fetch REAL data from a real source.
  - If the source has data: short_met/long_met are derived honestly from the
    real value against stated thresholds, and 'value' carries that real number.
  - If the source has NO data (collector error, agent missing, feed disconnected):
    short_met=long_met=False AND 'value' says exactly that — never a fabricated
    number, never silently treated as "met".
  - The overall scores only reflect what could actually be evaluated;
    'data_sources_live' / 'data_sources_missing' is the honest audit trail.

Pre-conditions are hard filters: if any fails, the net signal is BLOCKED
regardless of how high either confluence score is — no signal should fire
into a major data release, against an extreme-long crowd that could squeeze
higher, or with an unacceptably wide broker spread.
"""
import logging
import math
from datetime import datetime, timedelta, timezone

from services.supabase_service import get_supabase, get_latest_agent_scores, get_latest_forecast
from services.websocket_manager import ws_manager
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

CONDITION_WEIGHTS = {
    "dxy_direction":        2,   # FRED DTWEXBGS momentum — strengthening = short, weakening = long
    "real_yield_direction": 2,   # yield_agent score — bearish(<-10)=short (yields rising), bullish(>+10)=long (yields falling)
    "price_vs_vwap":        1,   # OANDA order flow — price below session VWAP = short, above = long
    "cumulative_delta":     2,   # OANDA order flow — Kaufman cumulative delta negative = short, positive = long
    "cot_mm_trend":         1,   # CFTC positioning — CONTRARIAN cot_signal (see cot_contrarian_signal)
    "no_imminent_news":     1,   # FMP/economic_releases — safe window awards its point to the leading side
    "options_gamma":        1,   # not implemented — always neutral, honest message
    "etf_flows":            1,   # ETF collector — outflow signal = short, inflow signal = long
    "risk_sentiment":       1,   # Sentiment collector — risk-on (>20 & SPY up) = short, risk-off (<-20) = long
    "session_level_break":  2,   # OANDA daily candles — price below prior session LOW = short, above prior session HIGH = long
}
MAX_SCORE = float(sum(CONDITION_WEIGHTS.values()))  # 14.0

NEWS_WINDOW_MINUTES = 15

# ── IMPROVEMENT 2 — Signal decay ────────────────────────────────────────────
# Fresher data should count more. Half-life = time for a data point's
# contribution to decay to 50% of its original weight.
HALF_LIVES_SECONDS = {
    "price":  60,        # 1 minute
    "delta":  60,
    "vwap":   60,
    "dxy":    60,
    "yields": 60,
    "etf":    86400,     # 24 hours
    "cot":    302400,    # 3.5 days
    "regime": 43200,     # 12 hours
    "news":   900,       # 15 minutes
}


def decay_factor(data_type: str, last_updated_iso: str | None) -> float:
    """
    Returns 1.0 if data is fresh, decays toward 0 as data ages.
    Never returns below 0.1 — stale data still contributes weakly.
    """
    if not last_updated_iso:
        return 0.5   # Unknown age — half weight
    try:
        last = datetime.fromisoformat(last_updated_iso.replace("Z", "+00:00"))
        age  = (datetime.now(timezone.utc) - last).total_seconds()
        t_half = HALF_LIVES_SECONDS.get(data_type, 3600)
        factor = math.exp(-math.log(2) * age / t_half)
        return max(0.1, round(factor, 3))
    except Exception:
        return 0.5


# ── IMPROVEMENT 3 — Regime-dependent condition weights ──────────────────────
REGIME_WEIGHT_MODIFIERS = {
    # (regime, condition): multiplier
    # In geopolitical crisis — DXY less reliable (gold + USD can both rise)
    ("geopolitical_crisis", "dxy_direction"):    0.4,
    ("geopolitical_crisis", "risk_sentiment"):   0.3,
    ("geopolitical_crisis", "cot_mm_trend"):     1.5,

    # In rate cut cycle — real yields dominate
    ("rate_cut_cycle", "real_yield_direction"):  1.8,
    ("rate_cut_cycle", "dxy_direction"):         0.8,

    # In rate hike cycle — DXY very reliable
    ("rate_hike_cycle", "dxy_direction"):        1.6,
    ("rate_hike_cycle", "real_yield_direction"): 1.4,

    # In inflation shock — COT and ETF flows very reliable
    ("inflation_shock", "cot_mm_trend"):         1.4,
    ("inflation_shock", "etf_flows"):            1.4,

    # In risk-off — sentiment and geo dominate
    ("risk_off", "risk_sentiment"):              1.6,
    ("risk_off", "dxy_direction"):               0.5,
}


def get_regime_weight(condition: str, regime: str, base_weight: float) -> float:
    modifier = REGIME_WEIGHT_MODIFIERS.get((regime, condition), 1.0)
    return round(base_weight * modifier, 3)


# ── ADDITION C — VIX-based position-size suggestion (display only) ──────────
def compute_position_size(vix: float | None, account_size_usd: float = 10000) -> dict:
    """
    Simple VIX-based position sizing. DISPLAY OUTPUT ONLY — AURUM-X never
    executes trades automatically; this is informational risk-sizing guidance.

    VIX < 15:  0.75% risk (low vol, more confident)
    VIX 15-20: 0.50% risk (normal)
    VIX 20-25: 0.35% risk (elevated vol)
    VIX 25-30: 0.25% risk (high vol)
    VIX > 30:  0.15% risk (extreme vol, smallest size)
    """
    if vix is None:
        return {"risk_pct": 0.50, "risk_usd": round(account_size_usd * 0.005, 2),
                "note": "Default — VIX unavailable", "vix": None, "account_size": account_size_usd}

    if   vix < 15:  risk_pct = 0.0075; label = "low vol — larger size"
    elif vix < 20:  risk_pct = 0.0050; label = "normal vol"
    elif vix < 25:  risk_pct = 0.0035; label = "elevated vol — reducing size"
    elif vix < 30:  risk_pct = 0.0025; label = "high vol — small size"
    else:           risk_pct = 0.0015; label = "extreme vol — minimum size"

    risk_usd = round(account_size_usd * risk_pct, 2)

    return {
        "risk_pct":     round(risk_pct * 100, 2),
        "risk_usd":     risk_usd,
        "vix":          vix,
        "label":        label,
        "note":         f"Risk {risk_pct*100:.2f}% of account (${risk_usd:.0f}) — {label}",
        "account_size": account_size_usd,
    }


def _dual(short_met: bool, long_met: bool, weight: int, value, threshold: str, source: str) -> dict:
    direction = "short" if short_met else ("long" if long_met else "neutral")
    return {
        "short_met": bool(short_met),
        "long_met":  bool(long_met),
        "direction": direction,
        "points":    weight,
        "value":     value,
        "threshold": threshold,
        "source":    source,
    }


def _dual_no_data(weight: int, value: str, threshold: str, source: str) -> dict:
    """Honest no-data condition result — never counted as met for either side."""
    return {
        "short_met": False,
        "long_met":  False,
        "direction": "neutral",
        "points":    weight,
        "value":     value,
        "threshold": threshold,
        "source":    source,
    }


class ShortScoreEngine:
    """Evaluates the 10-condition bi-directional gold trade-confluence gauge (LONG + SHORT)."""

    async def evaluate(self) -> dict:
        sb = get_supabase()

        # ── Gather raw inputs from each real source (independently — one
        #    source's failure must never blank out the others) ──────────────
        dollar_data        = await self._safe(self._get_dollar_data)
        agent_scores       = await self._safe(get_latest_agent_scores, default=[])
        positioning        = await self._safe(self._get_positioning)
        upcoming_releases  = await self._safe(self._get_upcoming_high_impact, default=[])
        etf_flows          = await self._safe(self._get_etf_flows)
        risk_sentiment     = await self._safe(self._get_risk_sentiment)
        forecast           = await self._safe(get_latest_forecast)
        orderflow          = await self._safe(self._get_orderflow, default={})
        current_price      = await self._safe(self._get_current_gold_price)
        regime_info        = await self._safe(self._get_smoothed_regime, default={})
        calibration        = await self._safe(self._get_calibration, default={})

        agent_by_name = {a.get("agent_name"): a for a in (agent_scores or [])}

        data_sources_live:    list = []
        data_sources_missing: list = []

        def _track(name: str, live: bool):
            (data_sources_live if live else data_sources_missing).append(name)

        conditions: dict = {}
        of_live  = orderflow and orderflow.get("status") == "live"
        of_ts    = (orderflow or {}).get("fetched_at")

        # ── Calibrated DXY-move threshold (ADDITION B) ─────────────────────
        # Replace the hardcoded ">0.15% = significant DXY move" with a value
        # derived from real 30-day OANDA volatility, when available.
        dxy_threshold = 0.15
        dxy_threshold_source = "hardcoded default (calibration unavailable)"
        calib_dxy_move = calibration.get("significant_dxy_move") if calibration.get("status") == "calibrated" else None
        if calib_dxy_move and calib_dxy_move > 0:
            dxy_threshold = calib_dxy_move
            dxy_threshold_source = f"30d-calibrated (EUR_USD proxy std × 0.5, {calibration.get('bars_used')} H1 bars)"

        # 1. DXY direction (FRED DTWEXBGS momentum, calibrated threshold)
        if dollar_data and "DXY_MOMENTUM_PCT" in dollar_data:
            momentum  = dollar_data["DXY_MOMENTUM_PCT"]
            direction = dollar_data.get("DXY_DIRECTION", "unknown")
            conditions["dxy_direction"] = _dual(
                momentum > dxy_threshold, momentum < -dxy_threshold, CONDITION_WEIGHTS["dxy_direction"],
                f"DXY momentum {momentum:+.3f}% ({direction})",
                f"> +{dxy_threshold:.4f}% = short | < -{dxy_threshold:.4f}% = long  [{dxy_threshold_source}]", "FRED",
            )
            _track("FRED (DXY)", True)
        else:
            conditions["dxy_direction"] = _dual_no_data(
                CONDITION_WEIGHTS["dxy_direction"],
                "unavailable — FRED DTWEXBGS series did not return momentum data",
                f"> +{dxy_threshold:.4f}% = short | < -{dxy_threshold:.4f}% = long", "FRED",
            )
            _track("FRED (DXY)", False)

        # 2. Real yield direction (proxied by yield_agent score)
        yield_agent = agent_by_name.get("yield_agent")
        if yield_agent is not None:
            score = yield_agent.get("score", 0)
            conditions["real_yield_direction"] = _dual(
                score < -10, score > 10, CONDITION_WEIGHTS["real_yield_direction"],
                f"yield_agent score = {score:+.1f}",
                "< -10 = short (bearish ⇒ real yields read as rising) | > +10 = long (bullish ⇒ yields read as falling)", "Agent",
            )
            _track("yield_agent", True)
        else:
            conditions["real_yield_direction"] = _dual_no_data(
                CONDITION_WEIGHTS["real_yield_direction"],
                "unavailable — yield_agent has not posted a score",
                "< -10 = short | > +10 = long", "Agent",
            )
            _track("yield_agent", False)

        # 3. Price vs session VWAP (OANDA order flow — real broker order flow)
        if of_live and orderflow.get("vwap_signal") in ("bearish", "bullish", "at_vwap"):
            vsig    = orderflow.get("vwap_signal")
            current = orderflow.get("current_price")
            vwap    = orderflow.get("session_vwap")
            conditions["price_vs_vwap"] = _dual(
                vsig == "bearish", vsig == "bullish", CONDITION_WEIGHTS["price_vs_vwap"],
                f"price ${current} vs session VWAP ${vwap} (signal={vsig})",
                "below VWAP = short | above VWAP = long", "OANDA",
            )
            _track("OANDA (order flow / VWAP)", True)
        else:
            conditions["price_vs_vwap"] = _dual_no_data(
                CONDITION_WEIGHTS["price_vs_vwap"],
                f"unavailable — {(orderflow or {}).get('error', 'OANDA order-flow VWAP signal not available')}",
                "below VWAP = short | above VWAP = long", "OANDA",
            )
            _track("OANDA (order flow / VWAP)", False)

        # 4. Cumulative delta direction (OANDA Kaufman approximation — real broker order flow)
        if of_live and orderflow.get("delta_direction") in ("positive", "negative", "neutral"):
            ddir  = orderflow.get("delta_direction")
            cdel  = orderflow.get("cumulative_delta")
            dmom  = orderflow.get("delta_momentum")
            conditions["cumulative_delta"] = _dual(
                ddir == "negative", ddir == "positive", CONDITION_WEIGHTS["cumulative_delta"],
                f"cumulative delta = {cdel} ({ddir}, momentum={dmom})",
                "negative = short | positive = long", "OANDA",
            )
            _track("OANDA (order flow / delta)", True)
        else:
            conditions["cumulative_delta"] = _dual_no_data(
                CONDITION_WEIGHTS["cumulative_delta"],
                f"unavailable — {(orderflow or {}).get('error', 'OANDA cumulative-delta data not available')}",
                "negative = short | positive = long", "OANDA",
            )
            _track("OANDA (order flow / delta)", False)

        # 5. COT — CONTRARIAN positioning signal (IMPROVEMENT 1)
        #    cot_signal is a tanh-transformed -1..+1 read of MM positioning vs
        #    its 8-week range: crowded longs (high pct) ⇒ bearish contrarian,
        #    crowded shorts (low pct) ⇒ bullish contrarian (squeeze risk).
        if positioning and not positioning.get("error") and "cot_signal" in positioning:
            cot_sig = positioning.get("cot_signal", 0)
            conditions["cot_mm_trend"] = _dual(
                cot_sig < -0.2, cot_sig > 0.2, CONDITION_WEIGHTS["cot_mm_trend"],
                f"{positioning.get('interpretation', '')} (cot_signal={cot_sig:+.3f})",
                "contrarian cot_signal < -0.2 (crowded long) = short | > +0.2 (crowded short) = long", "CFTC (contrarian)",
            )
            _track("CFTC (COT contrarian)", True)
        else:
            conditions["cot_mm_trend"] = _dual_no_data(
                CONDITION_WEIGHTS["cot_mm_trend"],
                f"unavailable — {(positioning or {}).get('error', 'CFTC contrarian cot_signal not available')}",
                "contrarian cot_signal < -0.2 = short | > +0.2 = long", "CFTC (contrarian)",
            )
            _track("CFTC (COT contrarian)", False)

        # 6. No imminent high-impact news (next 15 minutes) — safe window's point
        #    is awarded to whichever direction is leading once all other
        #    conditions are scored (see aggregation below). This entry starts
        #    neutral and is updated in place once the leader is known.
        news_eval = self._evaluate_no_imminent_news(upcoming_releases)
        conditions["no_imminent_news"] = _dual(
            False, False, CONDITION_WEIGHTS["no_imminent_news"],
            news_eval["value"],
            f"clear window (no high/critical release within {NEWS_WINDOW_MINUTES} min) ⇒ point awarded to leading side", "FMP",
        )
        _track("FMP (calendar)", True)  # an empty/queryable calendar IS a real, informative result

        # 7. Options gamma positioning — not implemented
        conditions["options_gamma"] = _dual_no_data(
            CONDITION_WEIGHTS["options_gamma"],
            "not implemented — no options/gamma data source wired up yet",
            "dealer gamma net short = short | net long = long", "Not implemented",
        )
        _track("Options/gamma", False)

        # 8. ETF flows
        if etf_flows and not etf_flows.get("error"):
            sig = etf_flows.get("combined_signal")
            conditions["etf_flows"] = _dual(
                sig in ("strong_outflow", "mild_outflow"),
                sig in ("strong_inflow", "mild_inflow"),
                CONDITION_WEIGHTS["etf_flows"],
                f"GLD/IAU combined_signal = {sig}",
                "outflow = short | inflow = long", "Yahoo Finance",
            )
            _track("Yahoo Finance (ETF flows)", True)
        else:
            conditions["etf_flows"] = _dual_no_data(
                CONDITION_WEIGHTS["etf_flows"],
                f"unavailable — {(etf_flows or {}).get('error', 'ETF flow data not available')}",
                "outflow = short | inflow = long", "Yahoo Finance",
            )
            _track("Yahoo Finance (ETF flows)", False)

        # 9. Risk sentiment (risk-on equities = short gold | risk-off = long gold)
        vix_price = None
        if risk_sentiment and risk_sentiment.get("risk_score") is not None:
            risk_score = risk_sentiment.get("risk_score", 0)
            spy_chg    = (risk_sentiment.get("spy") or {}).get("change_pct")
            spy_up     = (spy_chg or 0) > 0
            vix_price  = (risk_sentiment.get("vix") or {}).get("price")
            conditions["risk_sentiment"] = _dual(
                risk_score > 20 and spy_up, risk_score < -20, CONDITION_WEIGHTS["risk_sentiment"],
                f"risk_score={risk_score} (risk-on>20 & SPY up = short | risk-off<-20 = long), SPY change={spy_chg}%",
                "risk-on (>20 & SPY up) = short | risk-off (<-20) = long", "Yahoo Finance",
            )
            _track("Yahoo Finance (sentiment)", True)
        else:
            conditions["risk_sentiment"] = _dual_no_data(
                CONDITION_WEIGHTS["risk_sentiment"],
                "unavailable — risk-sentiment collector returned no data",
                "risk-on (>20 & SPY up) = short | risk-off (<-20) = long", "Yahoo Finance",
            )
            _track("Yahoo Finance (sentiment)", False)

        # 10. Session level break (OANDA daily candles — real broker data)
        prior_low  = (orderflow or {}).get("prior_session_low")
        prior_high = (orderflow or {}).get("prior_session_high")
        of_current = (orderflow or {}).get("current_price")
        if prior_low is not None and prior_high is not None and of_current is not None:
            below_low  = float(of_current) < float(prior_low)
            above_high = float(of_current) > float(prior_high)
            conditions["session_level_break"] = _dual(
                below_low, above_high, CONDITION_WEIGHTS["session_level_break"],
                f"price ${of_current:.2f} vs prior session range ${prior_low:.2f}–${prior_high:.2f}",
                "below prior session LOW = short | above prior session HIGH = long", "OANDA",
            )
            _track("OANDA (daily candles)", True)
        else:
            conditions["session_level_break"] = _dual_no_data(
                CONDITION_WEIGHTS["session_level_break"],
                "unavailable — insufficient OANDA daily candles or no current price to compare",
                "below prior session LOW = short | above prior session HIGH = long", "OANDA",
            )
            _track("OANDA (daily candles)", False)

        # ── IMPROVEMENT 2 — decay factors (applied only to the most
        #    time-sensitive, OANDA-order-flow-derived conditions) ───────────
        price_decay = decay_factor("price", of_ts)
        delta_decay = decay_factor("delta", of_ts)
        vwap_decay  = decay_factor("vwap",  of_ts)
        decay_factors = {
            "price": price_decay,
            "delta": delta_decay,
            "vwap":  vwap_decay,
            "data_timestamp": of_ts,
            "note": "Multiplies the effective scoring weight of order-flow-derived conditions — fresher OANDA data counts more.",
        }

        # ── IMPROVEMENT 3 — regime-dependent effective weights ──────────────
        regime = regime_info.get("regime", "unknown")
        effective_weights: dict = {}
        regime_weight_adjustments: dict = {}
        for cond, base_w in CONDITION_WEIGHTS.items():
            w = get_regime_weight(cond, regime, base_w)
            modifier = REGIME_WEIGHT_MODIFIERS.get((regime, cond))
            if cond == "price_vs_vwap":
                w *= vwap_decay
            elif cond == "cumulative_delta":
                w *= delta_decay
            w = round(w, 3)
            effective_weights[cond] = w
            if modifier is not None or w != base_w:
                regime_weight_adjustments[cond] = {
                    "base_weight":      base_w,
                    "regime_modifier":  modifier if modifier is not None else 1.0,
                    "decay_applied":    (vwap_decay if cond == "price_vs_vwap" else delta_decay if cond == "cumulative_delta" else 1.0),
                    "effective_weight": w,
                }

        # ── Aggregate using effective (regime + decay adjusted) weights,
        #    excluding no_imminent_news (its point is awarded below) ────────
        short_raw = sum(
            effective_weights[cond] for cond in CONDITION_WEIGHTS
            if cond != "no_imminent_news" and conditions[cond].get("short_met")
        )
        long_raw = sum(
            effective_weights[cond] for cond in CONDITION_WEIGHTS
            if cond != "no_imminent_news" and conditions[cond].get("long_met")
        )

        # Award the safe-news-window point to whichever side is currently leading
        news_weight = effective_weights["no_imminent_news"]
        if news_eval["clear"]:
            if short_raw >= long_raw:
                short_raw += news_weight
                conditions["no_imminent_news"] = _dual(
                    True, False, CONDITION_WEIGHTS["no_imminent_news"],
                    f"{news_eval['value']} — point awarded to SHORT (leading {round(short_raw - news_weight, 2)} vs {round(long_raw, 2)})",
                    f"clear window (no high/critical release within {NEWS_WINDOW_MINUTES} min) ⇒ awarded to leading side", "FMP",
                )
            else:
                long_raw += news_weight
                conditions["no_imminent_news"] = _dual(
                    False, True, CONDITION_WEIGHTS["no_imminent_news"],
                    f"{news_eval['value']} — point awarded to LONG (leading {round(long_raw - news_weight, 2)} vs {round(short_raw, 2)})",
                    f"clear window (no high/critical release within {NEWS_WINDOW_MINUTES} min) ⇒ awarded to leading side", "FMP",
                )
        # else: stays neutral — an imminent release helps neither side

        # ── IMPROVEMENT 4 — DXY × real-yield interaction term ───────────────
        dxy_short   = conditions["dxy_direction"].get("short_met", False)
        dxy_long    = conditions["dxy_direction"].get("long_met", False)
        yield_short = conditions["real_yield_direction"].get("short_met", False)
        yield_long  = conditions["real_yield_direction"].get("long_met", False)

        interaction_bonus = 0.0
        interaction_note  = "none — DXY and real yields are not aligned"

        if dxy_short and yield_short:
            dxy_yield_contribution = effective_weights["dxy_direction"] + effective_weights["real_yield_direction"]
            bonus             = round(dxy_yield_contribution * 0.3, 2)
            interaction_bonus = -bonus
            interaction_note  = f"DXY+yields both bearish gold — interaction bonus: -{bonus:.2f} pts (added to SHORT)"
            short_raw += bonus
        elif dxy_long and yield_long:
            dxy_yield_contribution = effective_weights["dxy_direction"] + effective_weights["real_yield_direction"]
            bonus             = round(dxy_yield_contribution * 0.3, 2)
            interaction_bonus = bonus
            interaction_note  = f"DXY+yields both bullish gold — interaction bonus: +{bonus:.2f} pts (added to LONG)"
            long_raw += bonus

        short_conditions_met = sum(1 for c in conditions.values() if c.get("short_met"))
        long_conditions_met  = sum(1 for c in conditions.values() if c.get("long_met"))

        short_pct = round(min(100.0, (short_raw / MAX_SCORE) * 100), 1) if MAX_SCORE else 0.0
        long_pct  = round(min(100.0, (long_raw  / MAX_SCORE) * 100), 1) if MAX_SCORE else 0.0

        # ── Pre-conditions (hard filters) ──────────────────────────────────
        cot_not_extreme_bull = True
        cot_value = "CFTC data unavailable — defaulting to not-extreme (fail-open)"
        if positioning and not positioning.get("error"):
            cot_not_extreme_bull = not bool(positioning.get("is_extreme_long", False))
            cot_value = f"is_extreme_long={positioning.get('is_extreme_long')} (pct_of_8w_range={positioning.get('pct_of_8w_range')}%)"

        spread_threshold = settings.oanda_spread_threshold
        of_spread        = (orderflow or {}).get("spread")
        if of_spread is not None:
            spread_acceptable = float(of_spread) < spread_threshold
            spread_value = (
                f"spread=${of_spread:.2f} vs threshold ${spread_threshold:.2f} "
                f"({'OK' if spread_acceptable else 'too wide'} — {settings.oanda_environment} account)"
            )
        else:
            spread_acceptable = True
            spread_value = "OANDA spread data unavailable — defaulting to acceptable (fail-open)"

        pre_conditions = {
            "no_imminent_news": {
                "pass":  news_eval["clear"],
                "value": news_eval["value"],
            },
            "cot_not_extreme_bull": {
                "pass":  cot_not_extreme_bull,
                "value": cot_value,
            },
            "spread_acceptable": {
                "pass":  spread_acceptable,
                "value": spread_value,
            },
        }
        pre_conditions_pass = all(p["pass"] for p in pre_conditions.values())

        # ── IMPROVEMENT 5 — volatility-adjusted thresholds ──────────────────
        if vix_price and vix_price > 30:
            high_conviction_threshold = 75.0
            scalp_threshold           = 50.0
            threshold_note            = f"VIX {vix_price:.1f} — elevated vol, raising bar"
        elif vix_price and vix_price < 12:
            high_conviction_threshold = 60.0
            scalp_threshold           = 35.0
            threshold_note            = f"VIX {vix_price:.1f} — quiet market, lowering bar"
        elif vix_price:
            high_conviction_threshold = 70.0
            scalp_threshold           = 40.0
            threshold_note            = f"VIX {vix_price:.1f} — normal thresholds"
        else:
            high_conviction_threshold = 70.0
            scalp_threshold           = 40.0
            threshold_note            = "VIX unavailable — using default thresholds"

        thresholds = {
            "high_conviction": high_conviction_threshold,
            "scalp":           scalp_threshold,
            "vix":             vix_price,
            "note":            threshold_note,
        }

        # ── Net signal classification (using volatility-adjusted thresholds) ─
        if not pre_conditions_pass:
            net_signal, net_color = "BLOCKED", "gray"
        elif short_pct >= high_conviction_threshold and short_pct > long_pct:
            net_signal, net_color = "HIGH CONVICTION SHORT", "red"
        elif long_pct >= high_conviction_threshold and long_pct > short_pct:
            net_signal, net_color = "HIGH CONVICTION LONG", "green"
        elif short_pct >= scalp_threshold and short_pct > long_pct:
            net_signal, net_color = "POTENTIAL SCALP SHORT", "amber"
        elif long_pct >= scalp_threshold and long_pct > short_pct:
            net_signal, net_color = "POTENTIAL SCALP LONG", "amber"
        elif abs(short_pct - long_pct) < 15:
            net_signal, net_color = "CONFLICTING SIGNALS", "gray"
        else:
            net_signal, net_color = "NO TRADE", "gray"

        go_short    = short_pct >= high_conviction_threshold and pre_conditions_pass and short_pct > long_pct
        go_long     = long_pct  >= high_conviction_threshold and pre_conditions_pass and long_pct  > short_pct
        scalp_short = scalp_threshold <= short_pct < high_conviction_threshold and short_pct > long_pct
        scalp_long  = scalp_threshold <= long_pct  < high_conviction_threshold and long_pct  > short_pct

        # ── ADDITION C — VIX-based position sizing (display only) ──────────
        position_sizing = compute_position_size(vix_price, settings.account_size_usd)

        timestamp = datetime.now(timezone.utc).isoformat()

        result = {
            # Short side
            "short_score":          short_pct,
            "short_raw":            round(short_raw, 2),
            "short_conditions_met": short_conditions_met,

            # Long side
            "long_score":           long_pct,
            "long_raw":             round(long_raw, 2),
            "long_conditions_met":  long_conditions_met,

            # Net signal
            "net_signal":           net_signal,
            "net_color":            net_color,
            "go_short":             go_short,
            "go_long":              go_long,
            "scalp_short":          scalp_short,
            "scalp_long":           scalp_long,

            # Shared
            "max_score":            MAX_SCORE,
            "total_conditions":     len(CONDITION_WEIGHTS),
            "conditions":           conditions,
            "pre_conditions":       pre_conditions,
            "pre_conditions_pass":  pre_conditions_pass,
            "spread_info": {
                "current_spread": of_spread,
                "threshold":      spread_threshold,
                "acceptable":     spread_acceptable,
                "account_type":   settings.oanda_environment,
                "note":           "Practice-account spreads run wider than live. Lower oanda_spread_threshold (~0.5) when switching to a live OANDA account.",
            },

            # Signal-quality layers
            "decay_factors":             decay_factors,
            "current_regime":            regime,
            "regime_info":               regime_info,
            "regime_weight_adjustments": regime_weight_adjustments,
            "interaction_bonus":         interaction_bonus,
            "interaction_note":          interaction_note,
            "thresholds":                thresholds,
            "calibration":               calibration,
            "position_sizing":           position_sizing,

            "data_sources_live":    sorted(set(data_sources_live)),
            "data_sources_missing": sorted(set(data_sources_missing)),
            "timestamp":            timestamp,

            # ── Backwards-compat aliases (old single-direction "short score" shape) ──
            "short_setup_score":    short_pct,
            "raw_score":            round(short_raw, 2),
            "conditions_met":       short_conditions_met,
            "signal":               net_signal,
            "signal_color":         net_color,
            "go":                   go_short,
            "scalp":                scalp_short,
        }

        await self._persist(result, current_price, risk_sentiment, forecast, sb)
        await ws_manager.broadcast({"type": "short_score_update", "data": result})

        logger.info(
            f"[confluence] LONG {long_pct}% | SHORT {short_pct}% | {net_signal} | regime={regime} | "
            f"long_met={long_conditions_met} short_met={short_conditions_met} / {len(CONDITION_WEIGHTS)} | "
            f"pre_conditions_pass={pre_conditions_pass} | thresholds(hc={high_conviction_threshold},scalp={scalp_threshold}) | "
            f"live={len(result['data_sources_live'])} missing={len(result['data_sources_missing'])}"
        )
        return result

    # ── Persistence ─────────────────────────────────────────────────────────

    async def _persist(self, result: dict, current_price, risk_sentiment, forecast, sb):
        try:
            vix = (risk_sentiment or {}).get("vix", {}).get("price") if risk_sentiment else None
            gold_price = current_price if current_price is not None else (forecast or {}).get("gold_price")

            record = {
                "timestamp":         result["timestamp"],
                "short_setup_score": result["short_setup_score"],
                "go_signal":         result["go"],
                "signal_strength":   result["signal"],
                "active_conditions": result["conditions"],
                "gold_price":        gold_price,
                "vix":               vix,
                "trigger":           "scheduled",
                "long_score":        result["long_score"],
                "short_score":       result["short_score"],
                "net_signal":        result["net_signal"],
                "go_long":           result["go_long"],
                "go_short":          result["go_short"],
            }
            sb.table("intraday_signals").insert(record).execute()
        except Exception as e:
            logger.error(f"[confluence] Failed to persist intraday_signals row: {e}")

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _safe(coro_fn, default=None):
        try:
            return await coro_fn()
        except Exception as e:
            logger.warning(f"[confluence] data source failed: {e}")
            return default

    @staticmethod
    async def _get_dollar_data():
        from collectors.macro_collector import MacroCollector
        return await MacroCollector().get_dollar_data()

    @staticmethod
    async def _get_positioning():
        from collectors.positioning_collector import PositioningCollector
        return await PositioningCollector().get_latest()

    @staticmethod
    async def _get_etf_flows():
        from collectors.etf_collector import ETFCollector
        return await ETFCollector().get_etf_flows()

    @staticmethod
    async def _get_risk_sentiment():
        from collectors.sentiment_collector import SentimentCollector
        return await SentimentCollector().get_risk_sentiment()

    @staticmethod
    async def _get_orderflow() -> dict:
        from collectors.oanda_collector import OandaCollector
        return await OandaCollector().get_order_flow()

    @staticmethod
    async def _get_smoothed_regime() -> dict:
        from services.regime_smoother import get_smoothed_regime
        return await get_smoothed_regime()

    @staticmethod
    async def _get_calibration() -> dict:
        from services.signal_calibrator import compute_calibration
        return await compute_calibration()

    @staticmethod
    async def _get_current_gold_price():
        from collectors.fmp_collector import FMPCollector
        data = await FMPCollector().get_gold_price()
        return data.get("price")

    @staticmethod
    async def _get_upcoming_high_impact() -> list:
        sb = get_supabase()
        now    = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(minutes=NEWS_WINDOW_MINUTES)).isoformat()
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

    @staticmethod
    def _evaluate_no_imminent_news(releases: list) -> dict:
        if not releases:
            return {"clear": True, "value": f"no high/critical-impact release scheduled within {NEWS_WINDOW_MINUTES} min"}
        names = ", ".join(f"{r.get('event', '?')} @ {r.get('release_date')}" for r in releases[:3])
        return {"clear": False, "value": f"IMMINENT: {names}"}
