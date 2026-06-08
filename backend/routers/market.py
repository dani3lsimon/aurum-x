# backend/routers/market.py
from fastapi import APIRouter
import logging

router = APIRouter(prefix="/market", tags=["market"])
logger = logging.getLogger(__name__)


@router.get("/candles")
async def get_candles(granularity: str = "H1", count: int = 48):
    """
    Real OANDA OHLCV candles for XAU_USD — powers the price-action chart.
    granularity: M15 | H1 | H4 | D   (anything else falls back to H1)
    count: clamped to [4, 200]
    """
    from collectors.oanda_collector import OandaCollector
    allowed = ["M15", "H1", "H4", "D"]
    if granularity not in allowed:
        granularity = "H1"
    count = min(max(count, 4), 200)
    oanda = OandaCollector()
    return await oanda.get_candles("XAU_USD", granularity, count)


@router.get("/orderflow")
async def get_orderflow():
    """Real-time OANDA order-flow snapshot — VWAP, cumulative delta, POC/VAH/VAL, spread."""
    from collectors.oanda_collector import OandaCollector
    oanda = OandaCollector()
    return await oanda.get_order_flow()
