# backend/routers/regime.py
from fastapi import APIRouter
import logging

router = APIRouter(prefix="/regime", tags=["regime"])
logger = logging.getLogger(__name__)


@router.get("/smoothed")
async def get_smoothed_regime_endpoint():
    """
    24h-rolling-mode smoothed regime label with hysteresis — used by the
    Trade Confluence Engine to apply regime-dependent condition weights
    without flip-flopping on every instantaneous regime_agent run.
    """
    from services.regime_smoother import get_smoothed_regime
    return await get_smoothed_regime()
