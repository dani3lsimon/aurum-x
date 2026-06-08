# backend/routers/agents.py
from fastapi import APIRouter
from services.supabase_service import get_latest_agent_scores, get_supabase
from collectors.positioning_collector import PositioningCollector

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/scores")
async def get_agent_scores():
    return await get_latest_agent_scores()


@router.get("/cot")
async def get_cot_data():
    """Real CFTC public-API gold positioning (managed money primary signal). No key required."""
    collector = PositioningCollector()
    return await collector.get_latest()


@router.get("/cot/refresh")
async def refresh_cot_data():
    """Force-refresh CFTC data, bypassing the 6h cache."""
    collector = PositioningCollector()
    return await collector.update_from_cftc()


@router.get("/sentiment")
async def get_sentiment():
    """Real-time risk-on/off sentiment — VIX, SPY, copper, gold/copper ratio (Yahoo Finance)."""
    from collectors.sentiment_collector import SentimentCollector
    c = SentimentCollector()
    return await c.get_risk_sentiment()


@router.get("/etf-flows")
async def get_etf_flows():
    """Gold ETF flow signals — GLD/IAU price action as institutional-demand proxy (Yahoo Finance)."""
    from collectors.etf_collector import ETFCollector
    c = ETFCollector()
    return await c.get_etf_flows()


@router.get("/technical-fusion")
async def get_technical_fusion():
    """Senior-trader fusion of deterministic SMC price-action structure with
    fundamental agent scores and macro bias — produces a concrete trade thesis
    (direction, entry zone, invalidation, targets, conviction). Sonnet, 5-min cache."""
    from agents.technical_fusion_agent import TechnicalFusionAgent
    return await TechnicalFusionAgent().run()


@router.get("/history/{agent_name}")
async def get_agent_history(agent_name: str, limit: int = 50):
    sb = get_supabase()
    result = (
        sb.table("agent_scores")
        .select("*")
        .eq("agent_name", agent_name)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
