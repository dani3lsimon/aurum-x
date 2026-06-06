# backend/collectors/market_collector.py
import logging
from collectors.fmp_collector import FMPCollector

logger = logging.getLogger(__name__)


class MarketCollector:
    def __init__(self):
        self.fmp = FMPCollector()

    async def get_gold_price(self) -> dict:
        # 1. Latest price from Supabase gold_prices table (seeded by agent via FMP/cTrader MCP)
        try:
            from services.supabase_service import get_supabase
            sb = get_supabase()
            row = sb.table("gold_prices").select("price,source,timestamp").order("timestamp", desc=True).limit(1).execute()
            if row.data:
                price = float(row.data[0]["price"])
                if price > 500:
                    logger.info(f"Gold price from Supabase: ${price}")
                    return {"symbol": "XAUUSD", "price": price, "source": row.data[0].get("source", "db")}
        except Exception as e:
            logger.warning(f"Supabase gold price read failed: {e}")

        # 2. Fallback to FMP cache in Supabase cache table
        cached = await self.fmp.get_gold_price()
        if cached.get("price", 0) > 500:
            return cached

        logger.error("Gold price unavailable — no data in Supabase or FMP cache")
        return {"symbol": "XAUUSD", "price": 0, "source": "unavailable"}

    async def get_yield_data(self) -> dict:
        return await self.fmp.get_treasury_yields()

    async def get_currency_data(self) -> dict:
        return await self.fmp.get_forex_rates()

    async def get_commodity_data(self) -> dict:
        return await self.fmp.get_commodities()
