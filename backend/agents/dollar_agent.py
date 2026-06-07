# backend/agents/dollar_agent.py — HAIKU, 2-hr skip cache
# Switched from FMP forex (returns null on current plan tier) to FRED's free
# trade-weighted dollar index + bilateral FX series. No API key tier issues —
# FRED is the same free public source already powering macro/fed/yield/liquidity agents.
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.macro_collector import MacroCollector


def _val(entry):
    """Extract {value, date} from a _fetch_fred {series, latest, previous} blob, or None."""
    if not isinstance(entry, dict) or entry.get("error"):
        return None
    latest = entry.get("latest") or {}
    raw = latest.get("value")
    try:
        return {"value": float(raw), "date": latest.get("date")}
    except (TypeError, ValueError):
        return None


class DollarAgent(BaseAgent):
    def __init__(self):
        super().__init__("dollar_agent", "Interprets dollar strength and FX flows for gold impact",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.macro = MacroCollector()
        self.data_source = 'FRED'

    async def collect_data(self) -> dict:
        """
        OANDA live FX rates are the primary source (real-time bid/ask, no
        publish-lag) — FRED's daily trade-weighted dollar index is the honest
        fallback if OANDA is unreachable (e.g. bad/missing token). Either way
        the agent only ever reports real fetched values — never a blended or
        fabricated number.
        """
        from collectors.oanda_collector import OandaCollector
        oanda_fx = await OandaCollector().get_fx_rates()
        if oanda_fx:
            return {"source": "oanda", "fx_rates": oanda_fx}

        raw = await self.macro.get_dollar_data()
        return {
            "source":           "fred",
            "fx_rates":         None,
            "dxy_broad":        _val(raw.get("DXY_BROAD")),
            "dxy_major":        _val(raw.get("DXY_MAJOR")),
            "eurusd":           _val(raw.get("EURUSD")),
            "usdjpy":           _val(raw.get("USDJPY")),
            "gbpusd":           _val(raw.get("GBPUSD")),
            "usdchf":           _val(raw.get("USDCHF")),
            "dxy_momentum_pct": raw.get("DXY_MOMENTUM_PCT"),
            "dxy_direction":    raw.get("DXY_DIRECTION"),
            "dxy_latest_date":  raw.get("DXY_LATEST_DATE"),
            "dxy_compare_date": raw.get("DXY_COMPARE_DATE"),
        }

    def build_prompt(self, data: dict) -> str:
        source = data.get("source")

        # ── OANDA live FX (primary) ─────────────────────────────────────
        if source == "oanda":
            fx = data.get("fx_rates") or {}
            if not fx:
                return """NO DOLLAR DATA AVAILABLE — OANDA returned no live FX prices (empty pricing response).
Respond with JSON only: score=0, confidence=0, rationale="No data available — OANDA FX feed returned no prices", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

            def mid(pair):
                e = fx.get(pair)
                return e.get("mid") if e else None

            return f"""Live dollar/FX data for gold impact (source: OANDA v20 REST API — real-time broker bid/ask mid-prices, no publish lag):

MAJOR FX PAIRS (live mid-price):
- EUR_USD: {mid('EUR_USD')}   (rising = euro strength = USD weakness, often bullish gold)
- USD_JPY: {mid('USD_JPY')}   (falling = yen strengthening = safe-haven bid, often bullish gold)
- GBP_USD: {mid('GBP_USD')}
- USD_CHF: {mid('USD_CHF')}   (falling = franc strengthening = safe-haven bid, often bullish gold)
- USD_CNH: {mid('USD_CNH')}
- AUD_USD: {mid('AUD_USD')}   (commodity-currency proxy — often correlates with risk appetite)

Rules:
- A broadly rising USD against these majors (EUR/GBP/AUD falling, USD_JPY/USD_CHF rising) = dollar strength = headwind for gold (bearish)
- A broadly falling USD (EUR/GBP/AUD rising, USD_JPY/USD_CHF falling) = dollar weakness = tailwind for gold (bullish)
- JPY or CHF strengthening vs USD while other pairs are mixed = safe-haven rotation = supportive of gold even without broad dollar weakness

Cite at least two specific live pair levels (with their actual numeric values) in your rationale and key_factors — no generic statements.
Respond with JSON only. No preamble."""

        # ── FRED daily series (honest fallback) ─────────────────────────
        if not data.get("dxy_broad") and not data.get("eurusd"):
            return """NO DOLLAR DATA AVAILABLE — both OANDA (live FX) and FRED (DTWEXBGS, DEXUSEU and related daily series) returned no usable data.
Respond with JSON only: score=0, confidence=0, rationale="No data available — OANDA FX feed and FRED dollar/FX series both unreachable", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

        return f"""Dollar-strength data for gold impact (fallback source: FRED — OANDA live FX was unreachable; these are free public daily-published series, no proxy/estimate):

BROAD TRADE-WEIGHTED USD INDEX (DTWEXBGS — direct DXY-equivalent signal):
- Latest level: {data.get('dxy_broad')}
- Momentum vs ~1 week prior: {data.get('dxy_momentum_pct')}% ({data.get('dxy_direction')}) — comparing {data.get('dxy_compare_date')} -> {data.get('dxy_latest_date')}
- Major-currencies index (DTWEXM): {data.get('dxy_major')}

BILATERAL FX (vs USD):
- EURUSD, USD per EUR: {data.get('eurusd')}
- USDJPY, JPY per USD: {data.get('usdjpy')}   (falling = yen strengthening = safe-haven bid, often bullish gold)
- GBPUSD, USD per GBP: {data.get('gbpusd')}
- USDCHF, CHF per USD: {data.get('usdchf')}   (falling = franc strengthening = safe-haven bid, often bullish gold)

Rules:
- Strengthening broad USD index = headwind for gold (bearish); weakening = tailwind (bullish)
- JPY or CHF strengthening vs USD while the broad index is flat/falling = broad safe-haven rotation = supportive of gold
- A momentum reading near 0% with mixed FX moves = no clear dollar-driven edge (neutral)

Cite the actual DTWEXBGS level, its momentum %, and at least one specific FX rate in your rationale and key_factors — no generic statements.
Respond with JSON only. No preamble."""
