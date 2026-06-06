# backend/agents/historical_agent.py — HAIKU, 6-hr skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_HEAVY
from collectors.fmp_collector import FMPCollector
from collectors.macro_collector import MacroCollector
from services.supabase_service import get_supabase

# Known gold historical analogs — used when historical_environments table is empty
HARDCODED_ANALOGS = [
    {"period": "2018-2019", "regime": "Late rate hike cycle → cuts", "fed_funds": "2.25-2.5% → 1.75%",
     "cpi": "2.0-2.5%", "gold_performance": "+18% during cut cycle", "analog_strength": "high"},
    {"period": "2007-2008", "regime": "Pre-recession rate cuts", "fed_funds": "5.25% → 0.25%",
     "cpi": "2-4%", "gold_performance": "+30% during easing", "analog_strength": "moderate"},
    {"period": "2020-2021", "regime": "QE / zero rates / ATH",  "fed_funds": "0-0.25%",
     "cpi": "1.5-7%", "gold_performance": "+25% to $2075 ATH", "analog_strength": "moderate"},
    {"period": "2022-2023", "regime": "Aggressive rate hike cycle", "fed_funds": "0% → 5.5%",
     "cpi": "7-9% → 3.5%", "gold_performance": "-5% during hikes, recovered on pivot", "analog_strength": "moderate"},
    {"period": "2024-2025", "regime": "Rate cut cycle begins, gold ATH", "fed_funds": "5.5% → 4.25%",
     "cpi": "3-3.5%", "gold_performance": "+35% to $3300 ATH", "analog_strength": "very high"},
]


class HistoricalAgent(BaseAgent):
    def __init__(self):
        super().__init__("historical_agent", "Finds historical analogs to current environment",
                         model=MODEL_HAIKU, skip_ttl=CACHE_TTL_HEAVY)
        self.fmp  = FMPCollector()
        self.fred = MacroCollector()

    async def collect_data(self) -> dict:
        yields = await self.fmp.get_treasury_yields()
        macro  = await self.fred.get_latest_indicators()
        sb     = get_supabase()
        hist   = sb.table("historical_environments").select("*").limit(10).execute()

        current = {
            "US10Y":    yields.get("US10Y"),
            "CPI":      macro.get("CPI", {}).get("latest", {}).get("value") if isinstance(macro.get("CPI"), dict) else None,
            "FED_FUNDS": macro.get("FED_FUNDS", {}).get("latest", {}).get("value") if isinstance(macro.get("FED_FUNDS"), dict) else None,
            "REAL_YIELD_10Y": macro.get("REAL_YIELD_10Y", {}).get("latest", {}).get("value") if isinstance(macro.get("REAL_YIELD_10Y"), dict) else None,
        }

        # Use hardcoded analogs when DB is empty
        history = hist.data if hist.data else HARDCODED_ANALOGS

        return {"current": current, "history": history}

    def build_prompt(self, data: dict) -> str:
        return f"""Current macro: {data.get('current', {})}
Historical gold periods: {data.get('history', [])}
Match to closest analog. Score gold based on what gold did in that period.
Respond with JSON only. No preamble."""
