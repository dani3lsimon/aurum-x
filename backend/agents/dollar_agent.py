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
        raw = await self.macro.get_dollar_data()
        return {
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
            "source": "FRED — DTWEXBGS (Trade-Weighted Broad Dollar Index) + bilateral FX series",
        }

    def build_prompt(self, data: dict) -> str:
        if not data.get("dxy_broad") and not data.get("eurusd"):
            return """NO DOLLAR DATA AVAILABLE — FRED returned no usable dollar/FX series (DTWEXBGS, DEXUSEU and related series all empty or erroring).
Respond with JSON only: score=0, confidence=0, rationale="No data available — FRED dollar/FX series unreachable", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

        return f"""Dollar-strength data for gold impact (source: FRED, free public series — no proxy/estimate, all values are actual published index/rate levels):

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
