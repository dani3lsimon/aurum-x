# backend/collectors/market_collector.py
# Primary: FMP MCP connector (via fmp_collector)
# Fallback: IBKR MCP connector
# No Alpha Vantage — removed
import logging
from collectors.fmp_collector import FMPCollector

logger = logging.getLogger(__name__)


class MarketCollector:
    """
    Routes market data requests to FMP MCP collector.
    Gold price, yields, FX pairs all served by FMP.
    IBKR MCP used for real-time snapshots where needed.
    """

    def __init__(self):
        self.fmp = FMPCollector()

    async def get_gold_price(self) -> dict:
        return await self.fmp.get_gold_price()

    async def get_yield_data(self) -> dict:
        return await self.fmp.get_treasury_yields()

    async def get_currency_data(self) -> dict:
        return await self.fmp.get_forex_rates()

    async def get_commodity_data(self) -> dict:
        return await self.fmp.get_commodities()
