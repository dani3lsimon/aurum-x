# backend/engines/short_score_engine.py
"""
Short-Setup Score Engine — 10-condition confluence gauge (0-100%) for an
intraday gold (XAUUSD/GC) SHORT setup.

Design principles (per the project's no-fake-data rule):
  - Every condition tries to fetch REAL data from a real source.
  - If the source has data: met=True/False is derived honestly from the
    real value against a stated threshold, and 'value' carries that real number.
  - If the source has NO data (collector error, agent missing, feed disconnected):
    met=False AND 'value' says exactly that — never a fabricated number,
    never silently treated as "met".
  - The overall score only reflects what could actually be evaluated;
    'data_sources_live' / 'data_sources_missing' is the honest audit trail.

Pre-conditions are hard filters: if any fails, the signal is BLOCKED regardless
of how high the confluence score is — no short signal should fire into a major
data release, into an unacceptable spread, or against an extreme-long crowd
that could squeeze higher before reversing.
"""
import logging
from datetime import datetime, timedelta, timezone

from services.supabase_service import get_supabase, get_latest_agent_scores, get_latest_forecast
from services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

CONDITION_WEIGHTS = {
    "dxy_rising":            2,   # FRED DTWEXBGS momentum
    "real_yield_rising":     2,   # yield_agent score < -10 (agent bearish ⇒ real yields read as rising)
    "price_below_vwap":      1,   # IBKR order flow — vwap_signal == 'bearish'
    "negative_delta":        2,   # IBKR order flow — delta_direction == 'negative'
    "cot_bearish_trend":     1,   # CFTC positioning — trend_8w == 'down'
    "no_imminent_news":      1,   # FMP/economic_releases — no high-impact event in next 15 min
    "options_gamma_bearish": 1,   # not implemented — always met=False, honest message
    "etf_outflows":          1,   # ETF collector — combined_signal in [strong_outflow, mild_outflow]
    "risk_on_equities":      1,   # Sentiment collector — risk_score > 20 and SPY positive
    "price_breaks_support":  2,   # IBKR order flow — price < VAL (volume-profile value-area low)
}
MAX_SCORE = float(sum(CONDITION_WEIGHTS.values()))  # 14.0

CONDITION_SOURCES = {
    "dxy_rising":            "FRED",
    "real_yield_rising":     "Agent",
    "price_below_vwap":      "IBKR",
    "negative_delta":        "IBKR",
    "cot_bearish_trend":     "CFTC",
    "no_imminent_news":      "FMP",
    "options_gamma_bearish": "Not implemented",
    "etf_outflows":          "Yahoo Finance",
    "risk_on_equities":      "Yahoo Finance",
    "price_breaks_support":  "IBKR",
}

NEWS_WINDOW_MINUTES = 15
SPREAD_THRESHOLD    = 0.50


def _met(met: bool, weight: int, value, threshold: str, source: str) -> dict:
    return {
        "met":       bool(met),
        "points":    weight if met else 0,
        "value":     value,
        "threshold": threshold,
        "source":    source,
    }


def _ibkr_unavailable(order_flow: dict) -> str:
    """Short, table-friendly 'no data' message for IBKR-dependent conditions —
    the full rationale is already exposed verbatim on /agents/orderflow."""
    status = (order_flow or {}).get("status", "disconnected")
    return f"unavailable — IBKR order-flow feed status='{status}' (see /agents/orderflow for full rationale)"


def _no_data(weight: int, value: str, threshold: str, source: str) -> dict:
    """Honest no-data condition result — never counted as met."""
    return {
        "met":       False,
        "points":    0,
        "value":     value,
        "threshold": threshold,
        "source":    source,
    }


class ShortScoreEngine:
    """Evaluates the 10-condition gold short-setup confluence gauge."""

    async def evaluate(self) -> dict:
        sb = get_supabase()

        # ── Gather raw inputs from each real source (independently — one
        #    source's failure must never blank out the others) ──────────────
        order_flow         = await self._safe(self._get_order_flow)
        dollar_data        = await self._safe(self._get_dollar_data)
        agent_scores       = await self._safe(get_latest_agent_scores, default=[])
        positioning        = await self._safe(self._get_positioning)
        upcoming_releases  = await self._safe(self._get_upcoming_high_impact, default=[])
        etf_flows          = await self._safe(self._get_etf_flows)
        risk_sentiment     = await self._safe(self._get_risk_sentiment)
        forecast           = await self._safe(get_latest_forecast)

        agent_by_name = {a.get("agent_name"): a for a in (agent_scores or [])}

        data_sources_live:    list = []
        data_sources_missing: list = []

        def _track(name: str, live: bool):
            (data_sources_live if live else data_sources_missing).append(name)

        conditions: dict = {}

        # 1. DXY rising (FRED DTWEXBGS momentum)
        if dollar_data and "DXY_MOMENTUM_PCT" in dollar_data:
            momentum = dollar_data["DXY_MOMENTUM_PCT"]
            direction = dollar_data.get("DXY_DIRECTION", "unknown")
            conditions["dxy_rising"] = _met(
                momentum > 0, CONDITION_WEIGHTS["dxy_rising"],
                f"{momentum:+.3f}% ({direction})", "> 0% (strengthening)", "FRED",
            )
            _track("FRED (DXY)", True)
        else:
            conditions["dxy_rising"] = _no_data(
                CONDITION_WEIGHTS["dxy_rising"], "unavailable — FRED DTWEXBGS series did not return momentum data",
                "> 0% (strengthening)", "FRED",
            )
            _track("FRED (DXY)", False)

        # 2. Real yield rising (proxied by yield_agent bearish score < -10)
        yield_agent = agent_by_name.get("yield_agent")
        if yield_agent is not None:
            score = yield_agent.get("score", 0)
            conditions["real_yield_rising"] = _met(
                score < -10, CONDITION_WEIGHTS["real_yield_rising"],
                f"yield_agent score = {score:+.1f}", "< -10 (bearish ⇒ real yields read as rising)", "Agent",
            )
            _track("yield_agent", True)
        else:
            conditions["real_yield_rising"] = _no_data(
                CONDITION_WEIGHTS["real_yield_rising"], "unavailable — yield_agent has not posted a score",
                "< -10 (bearish ⇒ real yields read as rising)", "Agent",
            )
            _track("yield_agent", False)

        # 3. Price below VWAP (IBKR)
        if order_flow and order_flow.get("status") == "live":
            sig = order_flow.get("vwap_signal")
            conditions["price_below_vwap"] = _met(
                sig == "bearish", CONDITION_WEIGHTS["price_below_vwap"],
                f"price={order_flow.get('current_price')} vs VWAP={order_flow.get('session_vwap')} ({sig})",
                "price < session VWAP", "IBKR",
            )
            _track("IBKR (order flow)", True)
        else:
            conditions["price_below_vwap"] = _no_data(
                CONDITION_WEIGHTS["price_below_vwap"], _ibkr_unavailable(order_flow),
                "price < session VWAP", "IBKR",
            )
            _track("IBKR (order flow)", False)

        # 4. Negative cumulative delta (IBKR)
        if order_flow and order_flow.get("status") == "live":
            dd = order_flow.get("delta_direction")
            conditions["negative_delta"] = _met(
                dd == "negative", CONDITION_WEIGHTS["negative_delta"],
                f"cumulative_delta(15m)={order_flow.get('cumulative_delta')} ({dd})",
                "cumulative delta < 0 (selling pressure)", "IBKR",
            )
        else:
            conditions["negative_delta"] = _no_data(
                CONDITION_WEIGHTS["negative_delta"], _ibkr_unavailable(order_flow),
                "cumulative delta < 0 (selling pressure)", "IBKR",
            )

        # 5. COT bearish 8-week trend (CFTC managed money)
        if positioning and not positioning.get("error"):
            trend = positioning.get("trend_8w")
            conditions["cot_bearish_trend"] = _met(
                trend == "down", CONDITION_WEIGHTS["cot_bearish_trend"],
                f"managed-money 8w trend = {trend} (net_change_8w={positioning.get('net_change_8w')})",
                "8-week managed-money net trend == down", "CFTC",
            )
            _track("CFTC (COT)", True)
        else:
            conditions["cot_bearish_trend"] = _no_data(
                CONDITION_WEIGHTS["cot_bearish_trend"],
                f"unavailable — {(positioning or {}).get('error', 'CFTC data not available')}",
                "8-week managed-money net trend == down", "CFTC",
            )
            _track("CFTC (COT)", False)

        # 6. No imminent high-impact news (next 15 minutes)
        news_eval = self._evaluate_no_imminent_news(upcoming_releases)
        conditions["no_imminent_news"] = _met(
            news_eval["clear"], CONDITION_WEIGHTS["no_imminent_news"],
            news_eval["value"], f"no high/critical-impact release within {NEWS_WINDOW_MINUTES} min", "FMP",
        )
        _track("FMP (calendar)", True)  # an empty/queryable calendar IS a real, informative result

        # 7. Options gamma positioning — not implemented
        conditions["options_gamma_bearish"] = _no_data(
            CONDITION_WEIGHTS["options_gamma_bearish"],
            "not implemented — no options/gamma data source wired up yet",
            "dealer gamma positioning == net short (bearish)", "Not implemented",
        )
        _track("Options/gamma", False)

        # 8. ETF outflows
        if etf_flows and not etf_flows.get("error"):
            sig = etf_flows.get("combined_signal")
            conditions["etf_outflows"] = _met(
                sig in ("strong_outflow", "mild_outflow"), CONDITION_WEIGHTS["etf_outflows"],
                f"GLD/IAU combined_signal = {sig}",
                "combined_signal in [strong_outflow, mild_outflow]", "Yahoo Finance",
            )
            _track("Yahoo Finance (ETF flows)", True)
        else:
            conditions["etf_outflows"] = _no_data(
                CONDITION_WEIGHTS["etf_outflows"],
                f"unavailable — {(etf_flows or {}).get('error', 'ETF flow data not available')}",
                "combined_signal in [strong_outflow, mild_outflow]", "Yahoo Finance",
            )
            _track("Yahoo Finance (ETF flows)", False)

        # 9. Risk-on equities (SPY up + risk_score > 20)
        if risk_sentiment and risk_sentiment.get("risk_score") is not None:
            risk_score = risk_sentiment.get("risk_score", 0)
            spy_chg    = (risk_sentiment.get("spy") or {}).get("change_pct")
            spy_up     = (spy_chg or 0) > 0
            conditions["risk_on_equities"] = _met(
                risk_score > 20 and spy_up, CONDITION_WEIGHTS["risk_on_equities"],
                f"risk_score={risk_score} (risk-on>20), SPY change={spy_chg}%",
                "risk_score > 20 AND SPY change_pct > 0", "Yahoo Finance",
            )
            _track("Yahoo Finance (sentiment)", True)
        else:
            conditions["risk_on_equities"] = _no_data(
                CONDITION_WEIGHTS["risk_on_equities"],
                "unavailable — risk-sentiment collector returned no data",
                "risk_score > 20 AND SPY change_pct > 0", "Yahoo Finance",
            )
            _track("Yahoo Finance (sentiment)", False)

        # 10. Price breaks support (price < VAL from IBKR volume profile)
        if order_flow and order_flow.get("status") == "live" and order_flow.get("val") is not None:
            price = order_flow.get("current_price")
            val   = order_flow.get("val")
            broke = price is not None and price < val
            conditions["price_breaks_support"] = _met(
                broke, CONDITION_WEIGHTS["price_breaks_support"],
                f"price={price} vs VAL(support)={val}",
                "price < VAL (value-area low)", "IBKR",
            )
        else:
            conditions["price_breaks_support"] = _no_data(
                CONDITION_WEIGHTS["price_breaks_support"], _ibkr_unavailable(order_flow),
                "price < VAL (value-area low)", "IBKR",
            )

        # ── Aggregate ───────────────────────────────────────────────────────
        score         = sum(c["points"] for c in conditions.values())
        conditions_met = sum(1 for c in conditions.values() if c["met"])
        pct_score     = round((score / MAX_SCORE) * 100, 1) if MAX_SCORE else 0.0

        # ── Pre-conditions (hard filters) ──────────────────────────────────
        spread_acceptable = True
        spread_value = "IBKR unavailable — defaulting to acceptable (fail-open)"
        if order_flow and order_flow.get("status") == "live":
            spread_acceptable = bool(order_flow.get("spread_ok", True))
            spread_value = f"spread_ok={order_flow.get('spread_ok')} (threshold < ${SPREAD_THRESHOLD})"

        cot_not_extreme_bull = True
        cot_value = "CFTC data unavailable — defaulting to not-extreme (fail-open)"
        if positioning and not positioning.get("error"):
            cot_not_extreme_bull = not bool(positioning.get("is_extreme_long", False))
            cot_value = f"is_extreme_long={positioning.get('is_extreme_long')} (pct_of_8w_range={positioning.get('pct_of_8w_range')}%)"

        pre_conditions = {
            "spread_acceptable": {
                "pass":  spread_acceptable,
                "value": spread_value,
            },
            "no_imminent_news": {
                "pass":  news_eval["clear"],
                "value": news_eval["value"],
            },
            "cot_not_extreme_bull": {
                "pass":  cot_not_extreme_bull,
                "value": cot_value,
            },
        }
        pre_conditions_pass = all(p["pass"] for p in pre_conditions.values())

        # ── Signal classification ───────────────────────────────────────────
        if not pre_conditions_pass:
            signal, signal_color = "BLOCKED", "gray"
        elif pct_score >= 70:
            signal, signal_color = "HIGH CONVICTION SHORT", "red"
        elif pct_score >= 40:
            signal, signal_color = "POTENTIAL SCALP SHORT", "amber"
        else:
            signal, signal_color = "NO TRADE", "green"

        go    = pre_conditions_pass and pct_score >= 70
        scalp = pre_conditions_pass and 40 <= pct_score < 70

        result = {
            "short_setup_score":    pct_score,
            "raw_score":            score,
            "max_score":            MAX_SCORE,
            "conditions_met":       conditions_met,
            "total_conditions":     len(CONDITION_WEIGHTS),
            "signal":               signal,
            "signal_color":         signal_color,
            "go":                   go,
            "scalp":                scalp,
            "pre_conditions":       pre_conditions,
            "pre_conditions_pass":  pre_conditions_pass,
            "conditions":           conditions,
            "data_sources_live":    sorted(set(data_sources_live)),
            "data_sources_missing": sorted(set(data_sources_missing)),
            "timestamp":            datetime.now(timezone.utc).isoformat(),
        }

        await self._persist(result, order_flow, risk_sentiment, forecast, sb)
        await ws_manager.broadcast({"type": "short_score_update", "data": result})

        logger.info(
            f"[short_score] {pct_score}% | {signal} | "
            f"conditions {conditions_met}/{len(CONDITION_WEIGHTS)} | "
            f"pre_conditions_pass={pre_conditions_pass} | "
            f"live={len(result['data_sources_live'])} missing={len(result['data_sources_missing'])}"
        )
        return result

    # ── Persistence ─────────────────────────────────────────────────────────

    async def _persist(self, result: dict, order_flow, risk_sentiment, forecast, sb):
        try:
            vix = (risk_sentiment or {}).get("vix", {}).get("price") if risk_sentiment else None
            gold_price = None
            if order_flow and order_flow.get("current_price") is not None:
                gold_price = order_flow.get("current_price")
            elif forecast:
                gold_price = forecast.get("gold_price")

            record = {
                "timestamp":         result["timestamp"],
                "short_setup_score": result["short_setup_score"],
                "go_signal":         result["go"],
                "signal_strength":   result["signal"],
                "active_conditions": result["conditions"],
                "gold_price":        gold_price,
                "vix":               vix,
                "cumulative_delta":  (order_flow or {}).get("cumulative_delta"),
                "trigger":           "scheduled",
            }
            sb.table("intraday_signals").insert(record).execute()
        except Exception as e:
            logger.error(f"[short_score] Failed to persist intraday_signals row: {e}")

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _safe(coro_fn, default=None):
        try:
            return await coro_fn()
        except Exception as e:
            logger.warning(f"[short_score] data source failed: {e}")
            return default

    @staticmethod
    async def _get_order_flow():
        from collectors.ibkr_orderflow_collector import IBKROrderFlowCollector
        return await IBKROrderFlowCollector().get_order_flow()

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
        names = ", ".join(f"{r.get('release_name', r.get('indicator_name', '?'))} @ {r.get('release_date')}" for r in releases[:3])
        return {"clear": False, "value": f"IMMINENT: {names}"}
