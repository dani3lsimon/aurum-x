# backend/agents/sentiment_agent.py — HAIKU, 2-hr skip cache
# Risk-on/off cross-asset sentiment + gold ETF flow analysis.
# Replaces historical_agent as Agent 09 in the primary score matrix
# (historical_agent keeps running as a 6-hr background enrichment task).
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD, MAX_TOKENS_SENTIMENT
from collectors.sentiment_collector import SentimentCollector
from collectors.etf_collector import ETFCollector


def _pct(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "N/A"


class SentimentAgent(BaseAgent):
    def __init__(self):
        super().__init__("sentiment_agent", "Risk-on/off sentiment and ETF flow analysis",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD, max_tokens=MAX_TOKENS_SENTIMENT)
        self.sentiment = SentimentCollector()
        self.etf       = ETFCollector()
        self.data_source = 'Yahoo Finance'

    async def collect_data(self) -> dict:
        import asyncio
        risk_data, etf_data = await asyncio.gather(
            self.sentiment.get_risk_sentiment(),
            self.etf.get_etf_flows(),
        )
        return {"risk_sentiment": risk_data, "etf_flows": etf_data}

    def build_prompt(self, data: dict) -> str:
        risk = data.get("risk_sentiment", {})
        etf  = data.get("etf_flows", {})
        vix  = risk.get("vix", {})
        spy  = risk.get("spy", {})
        gld  = etf.get("gld", {})
        iau  = etf.get("iau", {})

        if vix.get("price") is None and gld.get("price") is None:
            return """NO SENTIMENT DATA AVAILABLE — Yahoo Finance returned no usable VIX/SPY/ETF data.
Respond with JSON only: score=0, confidence=0, rationale="No data available — sentiment/ETF sources unreachable", regime="UNKNOWN", key_factors=["no data source"], signal_strength="neutral", directional_bias="neutral", data_quality="low", notable_risk="none".
No preamble."""

        return f"""Cross-asset risk sentiment and gold ETF flows for XAUUSD impact (sources: Yahoo Finance live quotes — real published prices, no proxy/estimate):

RISK SENTIMENT:
- VIX: {vix.get('price')} (change: {_pct(vix.get('change_pct'))})
- S&P 500 (SPY): {spy.get('price')} (change: {_pct(spy.get('change_pct'))})
- Gold/Copper ratio: {risk.get('gold_copper_ratio')}
- Risk regime: {risk.get('risk_regime')}
- Risk score: {risk.get('risk_score')} (-100=extreme fear/risk-off, +100=extreme greed/risk-on)
- Interpretation: {risk.get('interpretation')}

GOLD ETF FLOWS:
- GLD: ${gld.get('price')} ({_pct(gld.get('price_change_pct'))}) — signal: {gld.get('flow_signal')}
- IAU: ${iau.get('price')} ({_pct(iau.get('price_change_pct'))}) — signal: {iau.get('flow_signal')}
- Combined ETF flow: {etf.get('combined_signal')}

Rules:
- High VIX (>25) + falling SPY = risk-off = BULLISH gold (safe-haven demand)
- Low VIX (<15) + rising SPY = risk-on = BEARISH gold (capital flows to equities)
- Strong/mild ETF inflows = institutional gold demand = BULLISH; outflows = BEARISH
- Rising gold/copper ratio = gold outperforming = deflationary/fear signal = BULLISH

Cite the actual VIX level, SPY change %, and at least one ETF flow signal in your rationale and key_factors — no generic statements.
Respond with JSON only. No preamble."""
