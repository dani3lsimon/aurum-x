# backend/agents/orderflow_agent.py — HAIKU, 30-min skip cache
# Interprets GC (gold futures) intraday order flow — VWAP / cumulative delta /
# volume profile — for short-term directional read. Honest no-data when IBKR
# is disconnected (see collectors/ibkr_orderflow_collector.py for why).
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_FAST
from collectors.ibkr_orderflow_collector import IBKROrderFlowCollector


class OrderFlowAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            "orderflow_agent",
            "Interprets GC futures intraday order flow (VWAP/delta/volume profile) for gold",
            model=MODEL_HAIKU,
            skip_ttl=CACHE_TTL_FAST,
        )
        self.collector = IBKROrderFlowCollector()
        self.data_source = 'IBKR'

    async def collect_data(self) -> dict:
        return await self.collector.get_order_flow()

    def build_prompt(self, data: dict) -> str:
        if data.get("status") != "live":
            reason = (data.get("rationale") or "IBKR feed unavailable")[:180]
            return f"""NO LIVE ORDER-FLOW DATA — {reason}
Respond with JSON only:
{{"score": 0, "confidence": 0, "rationale": "No data available — {reason}", "regime": "unknown", "key_factors": ["no data source — IBKR order-flow feed not connected"], "signal_strength": "neutral", "directional_bias": "neutral", "data_quality": "low", "notable_risk": "No live order-flow feed connected — this read is uninformative until IBKR is reachable."}}
No preamble."""

        return f"""You are analysing GC (COMEX 100oz gold futures) intraday order flow as a short-term directional read for XAUUSD.

Current price:        {data.get('current_price')}
Session VWAP:         {data.get('session_vwap')}  (price is currently {data.get('vwap_signal')} relative to VWAP)
Cumulative delta (last 15min): {data.get('cumulative_delta')} — {data.get('delta_direction')} (negative = selling pressure dominant, positive = buying pressure dominant)
Volume profile — POC: {data.get('poc_price')}   VAH: {data.get('vah')}   VAL: {data.get('val')}
Bid/ask spread acceptable for execution: {data.get('spread_ok')}

Interpretation rules:
- Price below VWAP + negative cumulative delta = intraday bearish pressure building (sellers in control)
- Price breaking below VAL (Value Area Low) = momentum acceleration / prior support failing
- Price above VWAP + positive cumulative delta = intraday bullish pressure (buyers in control)
- Price pinned near POC with flat delta = balance / no clear edge

This is a SHORT-TERM intraday read, not a macro view — score and weight it accordingly (typically lower magnitude than macro agents unless order flow is extreme).

Respond with JSON only. No preamble."""
