# backend/agents/historical_agent.py — HAIKU, 6-hr skip cache
from agents.base_agent import BaseAgent
from config import MODEL_HAIKU, CACHE_TTL_HEAVY
from collectors.fmp_collector import FMPCollector
from collectors.macro_collector import MacroCollector
from services.supabase_service import get_supabase


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
        # Compress current env to key metrics only
        current = {
            "US10Y":    yields.get("US10Y"),
            "CPI":      macro.get("CPI", {}).get("latest", {}).get("value") if isinstance(macro.get("CPI"), dict) else None,
            "FED_FUNDS":macro.get("FED_FUNDS", {}).get("latest", {}).get("value") if isinstance(macro.get("FED_FUNDS"), dict) else None,
        }
        return {"current": current, "history": hist.data}

    def build_prompt(self, data: dict) -> str:
        return f"""Current: {data.get('current', {})}
Historical periods: {data.get('history', [])}
Match to closest analog. Score gold based on what gold did in that period.
Respond with JSON only. No preamble."""
