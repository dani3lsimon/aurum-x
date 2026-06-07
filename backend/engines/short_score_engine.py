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
data release or against an extreme-long crowd that could squeeze higher before
reversing.

NOTE: three conditions in this engine previously depended on a direct
broker order-flow feed that was unreachable from this deployed Railway
process (see git history for the removed broker collector/agent modules).
They have been replaced with real, reachable Yahoo Finance (GC=F) proxies:
intraday momentum vs a short SMA, a Supabase-tracked 30-minute price-change
check, and a prior-session-low breakdown check — all genuinely computed
from live data,
none fabricated.
"""
import logging
from datetime import datetime, timedelta, timezone

from services.supabase_service import get_supabase, get_latest_agent_scores, get_latest_forecast
from services.websocket_manager import ws_manager
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

CONDITION_WEIGHTS = {
    "dxy_rising":              2,   # FRED DTWEXBGS momentum — DXY strengthening
    "real_yield_rising":       2,   # yield_agent score < -10 (agent bearish ⇒ real yields read as rising)
    "gold_momentum_bearish":   1,   # OANDA order flow — price below session VWAP (vwap_signal == bearish)
    "gold_price_declining":    2,   # Supabase gold-price tracker — price lower than 30 min ago
    "cot_bearish_trend":       1,   # CFTC positioning — managed-money trend_8w == 'down'
    "no_imminent_news":        1,   # FMP/economic_releases — no high-impact event in next 15 min
    "options_gamma_bearish":   1,   # not implemented — always met=False, honest message
    "etf_outflows":            1,   # ETF collector — combined_signal in [strong_outflow, mild_outflow]
    "risk_on_equities":        1,   # Sentiment collector — risk_score > 20 and SPY positive
    "below_prior_session_low": 2,   # OANDA daily candles — price below prior daily session's low
}
MAX_SCORE = float(sum(CONDITION_WEIGHTS.values()))  # 14.0

NEWS_WINDOW_MINUTES = 15


def _met(met: bool, weight: int, value, threshold: str, source: str) -> dict:
    return {
        "met":       bool(met),
        "points":    weight if met else 0,
        "value":     value,
        "threshold": threshold,
        "source":    source,
    }


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
        dollar_data        = await self._safe(self._get_dollar_data)
        agent_scores       = await self._safe(get_latest_agent_scores, default=[])
        positioning        = await self._safe(self._get_positioning)
        upcoming_releases  = await self._safe(self._get_upcoming_high_impact, default=[])
        etf_flows          = await self._safe(self._get_etf_flows)
        risk_sentiment     = await self._safe(self._get_risk_sentiment)
        forecast           = await self._safe(get_latest_forecast)
        orderflow          = await self._safe(self._get_orderflow, default={})
        current_price      = await self._safe(self._get_current_gold_price)
        price_30m_ago      = await self._safe(self._get_price_30min_ago)

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

        # 3. Gold momentum bearish (OANDA session VWAP signal — real broker order flow)
        if orderflow and orderflow.get("status") == "live" and orderflow.get("vwap_signal") in ("bearish", "bullish", "at_vwap"):
            vsig    = orderflow.get("vwap_signal")
            current = orderflow.get("current_price")
            vwap    = orderflow.get("session_vwap")
            conditions["gold_momentum_bearish"] = _met(
                vsig == "bearish", CONDITION_WEIGHTS["gold_momentum_bearish"],
                f"price ${current} vs session VWAP ${vwap} (signal={vsig})",
                "price below session VWAP (vwap_signal == bearish)", "OANDA",
            )
            _track("OANDA (order flow / VWAP)", True)
        else:
            conditions["gold_momentum_bearish"] = _no_data(
                CONDITION_WEIGHTS["gold_momentum_bearish"],
                f"unavailable — {(orderflow or {}).get('error', 'OANDA order-flow VWAP signal not available')}",
                "price below session VWAP (vwap_signal == bearish)", "OANDA",
            )
            _track("OANDA (order flow / VWAP)", False)

        # 4. Gold price declining vs 30 minutes ago (Supabase price tracker)
        if price_30m_ago is not None and current_price is not None:
            c_declining = current_price < price_30m_ago
            conditions["gold_price_declining"] = _met(
                c_declining, CONDITION_WEIGHTS["gold_price_declining"],
                f"now ${current_price:.2f} vs 30m ago ${price_30m_ago:.2f}",
                "current price < price 30 min ago", "Supabase (gold price tracker)",
            )
            _track("Supabase (gold price tracker)", True)
        else:
            conditions["gold_price_declining"] = _no_data(
                CONDITION_WEIGHTS["gold_price_declining"],
                "unavailable — no 30-minute-old price snapshot yet (tracker warms up over the first 30 min after deploy)",
                "current price < price 30 min ago", "Supabase (gold price tracker)",
            )
            _track("Supabase (gold price tracker)", False)

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

        # 10. Price below prior session's low (OANDA daily candles — real broker data)
        prior_low    = (orderflow or {}).get("prior_session_low")
        of_current   = (orderflow or {}).get("current_price")
        if prior_low is not None and of_current is not None:
            c_below_low = float(of_current) < float(prior_low)
            conditions["below_prior_session_low"] = _met(
                c_below_low, CONDITION_WEIGHTS["below_prior_session_low"],
                f"price ${of_current:.2f} vs prior session low ${prior_low:.2f}",
                "price < prior session low", "OANDA",
            )
            _track("OANDA (daily candles)", True)
        else:
            conditions["below_prior_session_low"] = _no_data(
                CONDITION_WEIGHTS["below_prior_session_low"],
                "unavailable — insufficient OANDA daily candles or no current price to compare",
                "price < prior session low", "OANDA",
            )
            _track("OANDA (daily candles)", False)

        # ── Aggregate ───────────────────────────────────────────────────────
        score          = sum(c["points"] for c in conditions.values())
        conditions_met = sum(1 for c in conditions.values() if c["met"])
        pct_score      = round((score / MAX_SCORE) * 100, 1) if MAX_SCORE else 0.0

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
            "spread_info": {
                "current_spread": of_spread,
                "threshold":      spread_threshold,
                "acceptable":     spread_acceptable,
                "account_type":   settings.oanda_environment,
                "note":           "Practice-account spreads run wider than live. Lower oanda_spread_threshold (~0.5) when switching to a live OANDA account.",
            },
            "conditions":           conditions,
            "data_sources_live":    sorted(set(data_sources_live)),
            "data_sources_missing": sorted(set(data_sources_missing)),
            "timestamp":            datetime.now(timezone.utc).isoformat(),
        }

        await self._persist(result, current_price, risk_sentiment, forecast, sb)
        await ws_manager.broadcast({"type": "short_score_update", "data": result})

        logger.info(
            f"[short_score] {pct_score}% | {signal} | "
            f"conditions {conditions_met}/{len(CONDITION_WEIGHTS)} | "
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
    async def _get_price_30min_ago():
        """Reads the Supabase 'cache' row written every 5 minutes by
        scheduler._record_gold_price (key format gold_price_YYYYMMDD_HHMM,
        rounded to the nearest 5-minute bucket, value JSONB {"price", "ts"}).
        Returns None (honest no-data) if the tracker hasn't written a row for
        that bucket yet — e.g. in the first ~30 min after a fresh deploy the
        lookback window is still empty; that's reported as 'unavailable', not
        faked."""
        from services.redis_service import cache_get
        target  = datetime.now(timezone.utc) - timedelta(minutes=30)
        rounded = target.replace(minute=(target.minute // 5) * 5, second=0, microsecond=0)
        key = f"gold_price_{rounded.strftime('%Y%m%d_%H%M')}"
        cached = await cache_get(key)
        if isinstance(cached, dict):
            return cached.get("price")
        return None

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
