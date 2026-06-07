# backend/agents/positioning_agent.py — HAIKU, 2-hr skip cache
# Real CFTC public-API data only. No FMP, no hardcoded values.
# Primary signal = Managed Money (hedge funds, CTAs, CPOs) — the speculative
# traders whose crowding/positioning actually drives gold momentum/reversal risk.
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_STANDARD
from collectors.positioning_collector import PositioningCollector


class PositioningAgent(BaseAgent):
    def __init__(self):
        super().__init__("positioning_agent", "Interprets CFTC managed-money positioning for gold",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_STANDARD)
        self.collector = PositioningCollector()
        self.data_source = 'CFTC'

    async def collect_data(self) -> dict:
        return await self.collector.get_latest()

    def build_prompt(self, data: dict) -> str:
        if data.get("error"):
            return f"""NO CFTC DATA AVAILABLE — {data.get('error')}
Respond with JSON only: score=0, confidence=0, rationale="No data available — {data.get('error')}", regime="UNKNOWN", key_factors=["no data source"].
No preamble."""

        latest    = data.get("latest", {})
        all_weeks = data.get("all_weeks", [])

        weekly_table = "\n".join(
            f"  {w['date']}: mm_net={w['mm_net']:,.0f} ({w['mm_net_pct_oi']}% of OI)  "
            f"mm_long={w['mm_long']:,.0f}  mm_short={w['mm_short']:,.0f}  "
            f"comm_net={w['comm_net']:,.0f}"
            for w in all_weeks
        )

        return f"""You are analysing CFTC gold futures positioning for XAUUSD (real public CFTC data, dataset {data.get('dataset')}).

PRIMARY SIGNAL — Managed Money (hedge funds, CTAs, CPOs — the speculative traders):
Rising net long = institutional accumulation = bullish momentum.
Falling net long / rising net short = distribution = bearish momentum.
Extreme crowding in either direction raises reversal risk.

IMPORTANT: Extreme long positioning (>80th percentile) is a BEARISH contrarian
signal — crowded longs historically precede reversals. Extreme short positioning
(<20th percentile) is a BULLISH contrarian signal — short squeeze risk.
Computed contrarian read: {data.get('cot_signal_label', 'unknown')}
(cot_signal={data.get('cot_signal')} on a -1..+1 scale, {data.get('interpretation', '')}).

Weekly managed-money positioning (last {data.get('weeks_analysed')} weeks, oldest → newest):
{weekly_table}

Summary:
- 8-week trend (managed money net): {data.get('trend_8w', 'unknown').upper()}
- Net change over 8 weeks: {data.get('net_change_8w', 0):,.0f} contracts
- Current streak: {data.get('current_streak')}w consecutive {data.get('streak_direction')}
- Position as % of 8-week range: {data.get('pct_of_8w_range')}%
- Extreme long (crowded — reversal risk): {data.get('is_extreme_long')}
- Extreme short (coiled — squeeze risk): {data.get('is_extreme_short')}

Latest week ({latest.get('date')}):
- Managed money long:  {latest.get('mm_long', 0):,.0f}
- Managed money short: {latest.get('mm_short', 0):,.0f}
- Managed money NET:   {latest.get('mm_net', 0):,.0f} ({latest.get('mm_net_pct_oi', 0)}% of open interest)
- Commercial (producer/merchant) net: {latest.get('comm_net', 0):,.0f}  ← context only, smart-money contra-signal
- Open interest: {latest.get('open_interest', 0):,.0f}

Rules:
- Managed money extreme long (>80% of 8w range) = crowded = bearish contrarian signal
- Managed money extreme short (<20% of 8w range) = coiled = bullish contrarian signal
- Consecutive weekly increases in MM net = momentum building = bullish
- Commercial net very short = producers aggressively hedging into strength = bearish context
- Rising open interest with rising MM net = strong trend confirmation

Respond with JSON only. No preamble."""
