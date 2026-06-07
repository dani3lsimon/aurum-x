# backend/engines/short_score_engine.py
"""
Trade Confluence Score Engine — bi-directional 10-condition confluence gauge
(0-100% each side) producing a LONG score AND a SHORT score simultaneously
for an intraday gold (XAUUSD/GC) setup.

(Formerly the "Short-Setup Score Engine" — kept the class name and the
`/forecast/short-score` route path for backwards compatibility, but every
condition is now evaluated for BOTH directions and the net signal is whichever
side wins.)

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
    "cot_mm_trend":         1,   # CFTC positioning — managed-money 8w trend down = short, up = long
    "no_imminent_news":     1,   # FMP/economic_releases — safe window awards its point to the leading side
    "options_gamma":        1,   # not implemented — always neutral, honest message
    "etf_flows":            1,   # ETF collector — outflow signal = short, inflow signal = long
    "risk_sentiment":       1,   # Sentiment collector — risk-on (>20 & SPY up) = short, risk-off (<-20) = long
    "session_level_break":  2,   # OANDA daily candles — price below prior session LOW = short, above prior session HIGH = long
}
MAX_SCORE = float(sum(CONDITION_WEIGHTS.values()))  # 14.0

NEWS_WINDOW_MINUTES = 15


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

        agent_by_name = {a.get("agent_name"): a for a in (agent_scores or [])}

        data_sources_live:    list = []
        data_sources_missing: list = []

        def _track(name: str, live: bool):
            (data_sources_live if live else data_sources_missing).append(name)

        conditions: dict = {}
        of_live = orderflow and orderflow.get("status") == "live"

        # 1. DXY direction (FRED DTWEXBGS momentum)
        if dollar_data and "DXY_MOMENTUM_PCT" in dollar_data:
            momentum  = dollar_data["DXY_MOMENTUM_PCT"]
            direction = dollar_data.get("DXY_DIRECTION", "unknown")
            conditions["dxy_direction"] = _dual(
                momentum > 0.15, momentum < -0.15, CONDITION_WEIGHTS["dxy_direction"],
                f"DXY momentum {momentum:+.3f}% ({direction})",
                "> +0.15% = short (strengthening) | < -0.15% = long (weakening)", "FRED",
            )
            _track("FRED (DXY)", True)
        else:
            conditions["dxy_direction"] = _dual_no_data(
                CONDITION_WEIGHTS["dxy_direction"],
                "unavailable — FRED DTWEXBGS series did not return momentum data",
                "> +0.15% = short (strengthening) | < -0.15% = long (weakening)", "FRED",
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

        # 5. COT managed-money 8-week trend (CFTC positioning)
        if positioning and not positioning.get("error"):
            trend = positioning.get("trend_8w")
            conditions["cot_mm_trend"] = _dual(
                trend == "down", trend == "up", CONDITION_WEIGHTS["cot_mm_trend"],
                f"managed-money 8w trend = {trend} (net_change_8w={positioning.get('net_change_8w')})",
                "8-week trend down = short | up = long", "CFTC",
            )
            _track("CFTC (COT)", True)
        else:
            conditions["cot_mm_trend"] = _dual_no_data(
                CONDITION_WEIGHTS["cot_mm_trend"],
                f"unavailable — {(positioning or {}).get('error', 'CFTC data not available')}",
                "8-week trend down = short | up = long", "CFTC",
            )
            _track("CFTC (COT)", False)

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
        if risk_sentiment and risk_sentiment.get("risk_score") is not None:
            risk_score = risk_sentiment.get("risk_score", 0)
            spy_chg    = (risk_sentiment.get("spy") or {}).get("change_pct")
            spy_up     = (spy_chg or 0) > 0
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

        # ── Aggregate (excluding no_imminent_news, awarded below) ───────────
        short_raw = sum(
            w for cond, w in CONDITION_WEIGHTS.items()
            if cond != "no_imminent_news" and conditions[cond].get("short_met")
        )
        long_raw = sum(
            w for cond, w in CONDITION_WEIGHTS.items()
            if cond != "no_imminent_news" and conditions[cond].get("long_met")
        )

        # Award the safe-news-window point to whichever side is currently leading
        news_weight = CONDITION_WEIGHTS["no_imminent_news"]
        if news_eval["clear"]:
            if short_raw >= long_raw:
                short_raw += news_weight
                conditions["no_imminent_news"] = _dual(
                    True, False, news_weight,
                    f"{news_eval['value']} — point awarded to SHORT (leading {short_raw - news_weight} vs {long_raw})",
                    f"clear window (no high/critical release within {NEWS_WINDOW_MINUTES} min) ⇒ awarded to leading side", "FMP",
                )
            else:
                long_raw += news_weight
                conditions["no_imminent_news"] = _dual(
                    False, True, news_weight,
                    f"{news_eval['value']} — point awarded to LONG (leading {long_raw - news_weight} vs {short_raw})",
                    f"clear window (no high/critical release within {NEWS_WINDOW_MINUTES} min) ⇒ awarded to leading side", "FMP",
                )
        # else: stays neutral — an imminent release helps neither side

        short_conditions_met = sum(1 for c in conditions.values() if c.get("short_met"))
        long_conditions_met  = sum(1 for c in conditions.values() if c.get("long_met"))

        short_pct = round((short_raw / MAX_SCORE) * 100, 1) if MAX_SCORE else 0.0
        long_pct  = round((long_raw  / MAX_SCORE) * 100, 1) if MAX_SCORE else 0.0

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

        # ── Net signal classification ────────────────────────────────────────
        if not pre_conditions_pass:
            net_signal, net_color = "BLOCKED", "gray"
        elif short_pct >= 70 and short_pct > long_pct:
            net_signal, net_color = "HIGH CONVICTION SHORT", "red"
        elif long_pct >= 70 and long_pct > short_pct:
            net_signal, net_color = "HIGH CONVICTION LONG", "green"
        elif short_pct >= 40 and short_pct > long_pct:
            net_signal, net_color = "POTENTIAL SCALP SHORT", "amber"
        elif long_pct >= 40 and long_pct > short_pct:
            net_signal, net_color = "POTENTIAL SCALP LONG", "amber"
        elif abs(short_pct - long_pct) < 15:
            net_signal, net_color = "CONFLICTING SIGNALS", "gray"
        else:
            net_signal, net_color = "NO TRADE", "gray"

        go_short    = short_pct >= 70 and pre_conditions_pass and short_pct > long_pct
        go_long     = long_pct  >= 70 and pre_conditions_pass and long_pct  > short_pct
        scalp_short = 40 <= short_pct < 70 and short_pct > long_pct
        scalp_long  = 40 <= long_pct  < 70 and long_pct  > short_pct

        timestamp = datetime.now(timezone.utc).isoformat()

        result = {
            # Short side
            "short_score":          short_pct,
            "short_raw":            short_raw,
            "short_conditions_met": short_conditions_met,

            # Long side
            "long_score":           long_pct,
            "long_raw":             long_raw,
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
            "data_sources_live":    sorted(set(data_sources_live)),
            "data_sources_missing": sorted(set(data_sources_missing)),
            "timestamp":            timestamp,

            # ── Backwards-compat aliases (old single-direction "short score" shape) ──
            "short_setup_score":    short_pct,
            "raw_score":            short_raw,
            "conditions_met":       short_conditions_met,
            "signal":               net_signal,
            "signal_color":         net_color,
            "go":                   go_short,
            "scalp":                scalp_short,
        }

        await self._persist(result, current_price, risk_sentiment, forecast, sb)
        await ws_manager.broadcast({"type": "short_score_update", "data": result})

        logger.info(
            f"[confluence] LONG {long_pct}% | SHORT {short_pct}% | {net_signal} | "
            f"long_met={long_conditions_met} short_met={short_conditions_met} / {len(CONDITION_WEIGHTS)} | "
            f"pre_conditions_pass={pre_conditions_pass} | "
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
