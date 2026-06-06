# backend/collectors/market_collector.py
import logging
import httpx
from collectors.fmp_collector import FMPCollector
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MarketCollector:
    def __init__(self):
        self.fmp = FMPCollector()

    async def get_gold_price(self) -> dict:
        # 1. Yahoo Finance GC=F (gold futures, no auth required)
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                r = await client.get(
                    "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if r.status_code == 200:
                    meta = r.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price = meta.get("regularMarketPrice") or meta.get("previousClose") or 0
                    if price and float(price) > 500:
                        logger.info(f"Gold price from Yahoo Finance: ${price}")
                        return {"symbol": "XAUUSD", "price": float(price), "source": "yahoo"}
        except Exception as e:
            logger.warning(f"Yahoo Finance gold price failed: {e}")

        # 2. Fallback to FMP cache / Supabase
        cached = await self.fmp.get_gold_price()
        if cached.get("price", 0) > 500:
            return cached

        logger.error("All gold price sources failed — returning 0")
        return {"symbol": "XAUUSD", "price": 0, "source": "unavailable"}

    async def get_yield_data(self) -> dict:
        return await self.fmp.get_treasury_yields()

    async def get_currency_data(self) -> dict:
        return await self.fmp.get_forex_rates()

    async def get_commodity_data(self) -> dict:
        return await self.fmp.get_commodities()
