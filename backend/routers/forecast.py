# backend/routers/forecast.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from services.supabase_service import get_latest_forecast, get_forecast_history, get_latest_agent_scores, get_supabase
from services.redis_service import cache_get, cache_set, cache_delete
from services.websocket_manager import ws_manager
from config import get_settings
from datetime import datetime
import logging
import json
import anthropic

router = APIRouter(prefix="/forecast", tags=["forecast"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/latest")
async def get_latest():
    cached = await cache_get("latest_forecast")
    if cached:
        return cached
    return await get_latest_forecast() or {}


@router.get("/history")
async def get_history(hours: int = 48):
    return await get_forecast_history(hours=hours)


@router.post("/trigger")
async def trigger_manual_cycle(background_tasks: BackgroundTasks, request: Request):
    """Manually trigger a full agent cycle from the dashboard REFRESH INTEL button."""
    scheduler = request.app.state.scheduler
    background_tasks.add_task(
        scheduler._run_all_agents,
        trigger_event="manual_trigger"
    )
    logger.info("Manual agent cycle triggered via /forecast/trigger")
    return {
        "status":    "triggered",
        "message":   "Full agent cycle started",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/trigger/scenarios")
async def trigger_scenarios(background_tasks: BackgroundTasks, request: Request):
    """Manually trigger the scenario engine."""
    scheduler = request.app.state.scheduler
    background_tasks.add_task(scheduler._run_scenario_engine)
    return {"status": "triggered", "message": "Scenario engine started", "timestamp": datetime.utcnow().isoformat()}


@router.get("/brief")
async def get_intelligence_brief():
    """
    Generate a plain-English intelligence brief from current agent scores.
    Cached 30 minutes — expensive call, no need to regenerate every cycle.
    """
    cache_key = "intelligence_brief"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    forecast     = await get_latest_forecast()
    agent_scores = await get_latest_agent_scores()

    if not forecast or not agent_scores:
        return {"brief": None, "error": "insufficient data"}

    # Build context for Claude
    agents_summary = []
    for a in agent_scores:
        raw         = a.get("raw_data", {}) or {}
        key_factors = raw.get("key_factors", [])
        agents_summary.append({
            "agent":      a.get("agent_name", "").replace("_agent", "").upper(),
            "score":      a.get("score", 0),
            "bias":       raw.get("directional_bias", "neutral"),
            "strength":   raw.get("signal_strength", "weak"),
            "rationale":  a.get("rationale", ""),
            "key_factors": key_factors[:3],
        })

    prompt = f"""You are the Chief Macro Strategist at an institutional gold trading desk.

Based on the data below, write a plain-English intelligence brief about gold (XAUUSD).

Write it for an intelligent, non-technical reader. Avoid abbreviations, explain what things mean, use plain language.

Current Gold Price: ${forecast.get('gold_price', 'unknown')}
Overall Assessment: {forecast.get('bullish_prob', 0):.0f}% bullish / {forecast.get('bearish_prob', 0):.0f}% bearish
Model Confidence: {forecast.get('confidence_score', 0):.0f}%
Current Macro Regime: {forecast.get('macro_regime', 'unknown').replace('_', ' ')}

Agent Intelligence:
{json.dumps(agents_summary, indent=2)}

Write a JSON response with exactly these fields:
{{
  "headline": "One punchy sentence summarising the current gold market situation in plain English",
  "situation": "2-3 sentences explaining the overall environment. What is happening in markets right now and how does it affect gold? Use plain English. No abbreviations.",
  "supporting_gold": [
    "Plain English explanation of factor 1 supporting gold",
    "Plain English explanation of factor 2 supporting gold",
    "Plain English explanation of factor 3 supporting gold"
  ],
  "pressuring_gold": [
    "Plain English explanation of factor 1 pressuring gold",
    "Plain English explanation of factor 2 pressuring gold"
  ],
  "key_tension": "One paragraph explaining the most important contradiction or nuance in the current data. What makes this situation interesting or uncertain? Be specific about what the conflicting signals are.",
  "bottom_line": "2 sentences. What does all this mean for gold right now? Write it like you are explaining it to a smart friend over coffee — clear, direct, no jargon.",
  "watch_for": "One sentence. What is the single most important thing to monitor that could change this assessment?",
  "confidence_note": "One sentence explaining why the model confidence is at the level it is — what is causing uncertainty or certainty?"
}}

Rules:
- Never use: DXY, VWAP, COT, BPS, YoY, MoM, PCE, NFP, QT, QE or any other abbreviation without first explaining what it means
- Always explain what a metric means before citing its value (e.g. not 'VIX at 21' but 'the VIX fear gauge, which measures how much volatility investors expect in the stock market, is at 21 — an elevated level suggesting genuine concern')
- If there are contradictions in the data, highlight them explicitly — this is the most valuable insight
- supporting_gold and pressuring_gold must each have 2-3 items — never more
- Be honest about uncertainty — if signals are mixed, say so clearly

Return only the JSON object. No markdown. No preamble."""

    try:
        client   = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 1500,
            system     = "You are a senior macro strategist. Write clear, jargon-free intelligence briefs.",
            messages   = [{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        brief = json.loads(raw_text)
        brief["generated_at"]  = datetime.utcnow().isoformat()
        brief["gold_price"]    = forecast.get("gold_price")
        brief["bullish_prob"]  = forecast.get("bullish_prob")
        brief["bearish_prob"]  = forecast.get("bearish_prob")
        brief["confidence"]    = forecast.get("confidence_score")
        brief["regime"]        = forecast.get("macro_regime")

        await cache_set(cache_key, brief, ttl_seconds=1800)
        return brief

    except Exception as e:
        logger.error(f"Intelligence brief error: {e}")
        return {"brief": None, "error": str(e)}


@router.post("/brief/refresh")
async def refresh_intelligence_brief():
    await cache_delete("intelligence_brief")
    return await get_intelligence_brief()


@router.get("/short-score")
async def get_short_score():
    """
    Short-Setup Score Engine — 10-condition confluence gauge (0-100%) for an
    intraday gold SHORT setup. Cached 60s; the scheduler also re-evaluates and
    persists/broadcasts every 5 minutes (see scheduler._run_short_score).

    Honest by design: conditions whose data source is unreachable report
    met=False with a clear 'unavailable' value — see data_sources_missing.
    """
    cache_key = "short_setup_score"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    from engines.short_score_engine import ShortScoreEngine
    result = await ShortScoreEngine().evaluate()
    await cache_set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/calibration")
async def get_calibration():
    """
    30-day rolling volatility calibration computed from real OANDA H1 candles
    (gold + EUR_USD proxy for DXY) — replaces hardcoded "significant move"
    thresholds with statistics derived from actual recent market behaviour.
    Recomputed daily at 22:00 UTC by the scheduler; cached 24h.
    """
    from services.signal_calibrator import compute_calibration
    return await compute_calibration()


@router.get("/multi-tf")
async def get_multi_tf_signal():
    """
    Multi-timeframe bi-directional confluence engine — runs the same
    9-condition scoring at 15min/1h/4h on real OANDA candles, blends them
    (50/30/20 weighting) and surfaces the single highest-conviction
    timeframe + direction with edge strength, suggested risk %, and a
    volatility-derived stop-loss level. Cached 60s; scheduler re-evaluates
    every 5 minutes (see scheduler._run_multi_tf).
    """
    from engines.multi_tf_engine import evaluate_multi_tf
    return await evaluate_multi_tf()


@router.post("/multi-tf/refresh")
async def refresh_multi_tf():
    """Force a fresh multi-timeframe evaluation, bypassing the 60s cache."""
    from services.redis_service import cache_delete
    from engines.multi_tf_engine import evaluate_multi_tf
    await cache_delete("multi_tf_signal")
    return await evaluate_multi_tf()


@router.get("/signal-history")
async def get_signal_history_endpoint(limit: int = 100, timeframe: str | None = None):
    """Full signal journal — every recorded signal and its current outcome."""
    from services.signal_journal import get_signal_history
    return await get_signal_history(limit=limit, timeframe=timeframe)


@router.get("/signal-history/stats")
async def get_signal_stats():
    """Aggregate performance stats (win rate, TP hit rates, PnL) for the track record dashboard."""
    from services.signal_journal import get_performance_stats
    return await get_performance_stats()


@router.get("/signal-history/open")
async def get_open_signals():
    """Currently open signals (status='OPEN')."""
    sb = get_supabase()
    result = sb.table("signal_history").select("*").eq("status", "OPEN").execute()
    return result.data or []


@router.get("/short-score/history")
async def get_short_score_history(limit: int = 48):
    """Recent intraday_signals rows — score history for the ShortScoreWidget sparkline/log."""
    sb = get_supabase()
    result = (
        sb.table("intraday_signals")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        current = await get_latest_forecast()
        if current:
            await websocket.send_json({"type": "initial_state", "data": current})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
