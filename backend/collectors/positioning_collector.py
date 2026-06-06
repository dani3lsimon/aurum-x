# backend/collectors/positioning_collector.py
# Primary: FMP MCP commitmentOfTraders tool
# Fallback: CFTC direct download
import httpx
import logging
from collectors.fmp_collector import FMPCollector
from services.supabase_service import get_supabase

logger = logging.getLogger(__name__)


class PositioningCollector:
    CFTC_URL = "https://www.cftc.gov/dea/newcot/c_disagg.txt"
    GOLD_FUTURES_CODE = "088691"

    def __init__(self):
        self.fmp = FMPCollector()

    async def get_latest(self) -> dict:
        """Return the most recent COT data from Supabase + live FMP data."""
        sb = get_supabase()
        result = (
            sb.table("cftc_positioning")
            .select("*")
            .order("report_date", desc=True)
            .limit(5)
            .execute()
        )
        db_data = result.data

        # Try to augment with live FMP COT data
        try:
            fmp_cot = await self.fmp.get_cot_data("XAUUSD")
            if fmp_cot:
                return {
                    "latest_fmp": fmp_cot,
                    "historical_db": db_data,
                    "source": "fmp_mcp",
                }
        except Exception as e:
            logger.warning(f"FMP COT failed, using DB only: {e}")

        if not db_data:
            return {"status": "no_data", "message": "No positioning data available"}

        latest = db_data[0]
        historical = db_data[1:] if len(db_data) > 1 else []
        net_change = None
        if historical:
            net_change = (
                latest.get("managed_money_net", 0)
                - historical[0].get("managed_money_net", 0)
            )
        return {
            "latest": latest,
            "previous_periods": historical,
            "net_managed_money_change": net_change,
            "crowding_score": latest.get("crowding_score"),
            "extreme_positioning": latest.get("extreme_positioning"),
            "source": "supabase_db",
        }

    async def update_from_fmp(self):
        """Update CFTC positioning from FMP MCP connector."""
        try:
            cot_data = await self.fmp.get_cot_data("XAUUSD")
            if cot_data:
                sb = get_supabase()
                sb.table("cftc_positioning").upsert(
                    cot_data, on_conflict="report_date"
                ).execute()
                logger.info("CFTC data updated via FMP MCP")
        except Exception as e:
            logger.error(f"FMP COT update failed: {e}")
            await self._update_from_cftc_direct()

    async def _update_from_cftc_direct(self):
        """Fallback: parse CFTC raw file directly."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.CFTC_URL)
                resp.raise_for_status()
                lines = resp.text.strip().split("\n")
                for line in lines:
                    if self.GOLD_FUTURES_CODE in line:
                        fields = line.split(",")
                        if len(fields) > 30:
                            rd = {
                                "report_date":        fields[2].strip().strip('"'),
                                "commercial_long":    int(fields[8]) if fields[8].strip() else 0,
                                "commercial_short":   int(fields[9]) if fields[9].strip() else 0,
                                "noncommercial_long": int(fields[5]) if fields[5].strip() else 0,
                                "noncommercial_short":int(fields[6]) if fields[6].strip() else 0,
                                "open_interest":      int(fields[4]) if fields[4].strip() else 0,
                            }
                            rd["commercial_net"]    = rd["commercial_long"]    - rd["commercial_short"]
                            rd["noncommercial_net"] = rd["noncommercial_long"] - rd["noncommercial_short"]
                            sb = get_supabase()
                            sb.table("cftc_positioning").upsert(
                                rd, on_conflict="report_date"
                            ).execute()
                            logger.info(f"CFTC direct update: {rd['report_date']}")
                        break
        except Exception as e:
            logger.error(f"CFTC direct download failed: {e}")
