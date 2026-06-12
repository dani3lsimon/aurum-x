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


@router.get("/patterns")
async def get_smc_patterns():
    """Deterministic Smart Money Concepts pattern engine — swing structure,
    BOS/ChoCH, liquidity grabs, fair value gaps, order/breaker blocks,
    head & shoulders, double tops/bottoms — across 15min/1h/4h with a
    blended net confluence score and timeframe-alignment verdict."""
    from engines.patterns_engine import analyze_all
    return await analyze_all()


@router.get("/kronos/latest")
async def get_latest_kronos():
    """Latest cached Kronos-mini probabilistic forecasts per timeframe.
    Returns {'available': False} per timeframe if Kronos host is offline."""
    from services.redis_service import cache_get
    results = {}
    for tf in ['15min', '1h', '4h']:
        results[tf] = await cache_get(f'kronos_{tf}') or {'available': False}
    return results


@router.post("/kronos/refresh")
async def refresh_kronos(background_tasks: BackgroundTasks, request: Request):
    """Manually trigger a fresh Kronos forecast for all 3 timeframes."""
    scheduler = request.app.state.scheduler
    background_tasks.add_task(scheduler._run_kronos_forecast)
    return {"status": "triggered", "message": "Kronos forecast refresh started"}


@router.get("/kronos/accuracy")
async def get_kronos_accuracy():
    """Directional hit rate per timeframe. 'trusted' becomes True at n≥20
    and hit_rate>55% — that's when Kronos earns real weight in the fusion agent."""
    from services.kronos_tracker import get_accuracy_stats
    return await get_accuracy_stats()


@router.get("/economic-calendar")
async def get_economic_calendar(days: int = 7, debug: bool = False):
    """
    Medium + high impact economic events for the next N days (default 7).
    Events that directly move gold (CPI, FOMC, NFP, etc.) are flagged gold_relevant=true.
    Add ?debug=true to bypass cache and see fetch diagnostics.
    Cached 30 minutes.
    """
    cache_key = f"economic_calendar_{days}"
    if not debug:
        cached = await cache_get(cache_key)
        if cached:
            return cached
    try:
        from services.economic_calendar import fetch_economic_events
        events, diagnostics = await fetch_economic_events(days_ahead=days)
        result = {
            "status":      "ok",
            "events":      events,
            "fetched_at":  datetime.utcnow().isoformat(),
            "diagnostics": diagnostics,
        }
        if events:   # only cache if we got something
            await cache_set(cache_key, result, ttl_seconds=1800)
        return result
    except Exception as e:
        logger.error(f"Economic calendar error: {e}")
        return {"status": "error", "message": str(e), "events": []}


@router.get("/calendar-outcomes")
async def get_calendar_outcomes():
    """All manually tracked prediction outcomes (✓/✗) for the economic calendar."""
    import asyncio
    cache_key = "calendar_outcomes"
    cached = await cache_get(cache_key)
    if cached:
        return cached
    try:
        sb = get_supabase()
        result = await asyncio.to_thread(
            lambda: sb.table("calendar_outcomes").select("*").execute()
        )
        data = {"status": "ok", "outcomes": result.data or []}
        await cache_set(cache_key, data, ttl_seconds=60)
        return data
    except Exception as exc:
        logger.error(f"calendar-outcomes fetch error: {exc}")
        return {"status": "error", "outcomes": [], "message": str(exc)}


@router.post("/calendar-outcome")
async def upsert_calendar_outcome(payload: dict):
    """Save or update a ✓/✗ outcome for a released economic event."""
    import asyncio
    sb = get_supabase()
    row = {
        "event_key":  payload.get("event_key"),
        "event_name": payload.get("event_name"),
        "event_date": payload.get("event_date"),
        "event_type": payload.get("event_type"),
        "predicted":  payload.get("predicted"),
        "correct":    payload.get("correct"),
        "updated_at": datetime.utcnow().isoformat(),
    }
    await asyncio.to_thread(
        lambda: sb.table("calendar_outcomes").upsert(row, on_conflict="event_key").execute()
    )
    await cache_delete("calendar_outcomes")
    return {"status": "ok"}


@router.delete("/calendar-outcome/{event_key}")
async def delete_calendar_outcome(event_key: str):
    """Remove a tracked outcome (resets the toggle to unset)."""
    import asyncio
    sb = get_supabase()
    await asyncio.to_thread(
        lambda: sb.table("calendar_outcomes").delete().eq("event_key", event_key).execute()
    )
    await cache_delete("calendar_outcomes")
    return {"status": "deleted"}


@router.get("/event-patterns")
async def get_event_patterns():
    """Historical XAUUSD reaction stats per macro event type (Supabase event_patterns table)."""
    import asyncio
    cache_key = "event_patterns"
    cached = await cache_get(cache_key)
    if cached:
        return cached
    try:
        sb = get_supabase()
        result = await asyncio.to_thread(
            lambda: sb.table("event_patterns").select("*").order("event_type").execute()
        )
        patterns = result.data or []
        payload = {"status": "ok", "patterns": patterns}
        await cache_set(cache_key, payload, ttl_seconds=300)
        return payload
    except Exception as exc:
        logger.error(f"event-patterns fetch error: {exc}")
        return {"status": "error", "patterns": [], "message": str(exc)}


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


@router.post("/signal-history/backfill-r")
async def backfill_realized_r():
    """
    One-shot migration: back-fill realized_r, outcome_class, and portions_closed
    for all closed signals that were recorded before the R-multiple journal was
    introduced (i.e. rows where realized_r IS NULL).

    Derivation logic (mirrors _check_and_update_signal):
      - TP3 hit                         → realized_r = 0.50*1 + 0.25*2 + 0.25*3 = 1.625 → WIN
      - TP2 hit, stopped/expired after  → realized_r = 0.50*1 + 0.25*2 = 1.00          → WIN
      - TP1 hit, stopped at BE after    → realized_r = 0.50*1 = 0.50                    → WIN
      - Stopped with no TP              → realized_r = -1.0                             → LOSS
      - EXPIRED_PROFIT (no TPs tracked) → realized_r = +0.50 (estimate: TP1-equivalent) → WIN
      - EXPIRED_LOSS                    → realized_r = -1.0                             → LOSS
    """
    sb = get_supabase()

    # Fetch all closed rows missing realized_r
    rows = sb.table("signal_history") \
        .select("id, tp1_hit, tp2_hit, tp3_hit, result_label, status, risk_distance, risk_usd, stop_loss, entry_price") \
        .neq("status", "OPEN") \
        .is_("realized_r", "null") \
        .execute().data or []

    if not rows:
        return {"updated": 0, "message": "Nothing to backfill — all closed rows already have realized_r."}

    updated = 0
    errors  = 0
    for row in rows:
        try:
            tp1 = bool(row.get("tp1_hit"))
            tp2 = bool(row.get("tp2_hit"))
            tp3 = bool(row.get("tp3_hit"))
            rl  = row.get("result_label") or ""

            # Derive realized_r from which TPs were hit
            realized_r = 0.0
            if tp1: realized_r += 0.50 * 1.0
            if tp2: realized_r += 0.25 * 2.0
            if tp3: realized_r += 0.25 * 3.0

            if rl == "TP3" or tp3:
                outcome = "WIN"
            elif rl in ("STOPPED_BE_AFTER_TP",) or (tp1 and rl == "STOPPED"):
                outcome = "WIN" if realized_r > 0.01 else "BREAKEVEN"
            elif rl in ("STOPPED", "EXPIRED_LOSS") and not tp1:
                realized_r = -1.0
                outcome    = "LOSS"
            elif rl in ("TP1", "TP2", "EXPIRED_PROFIT") or tp1:
                outcome = "WIN"
            else:
                realized_r = -1.0
                outcome    = "LOSS"

            risk_dist = float(row.get("risk_distance") or 0)
            risk_usd  = float(row.get("risk_usd") or 0)
            realized_pts = round(realized_r * risk_dist, 2) if risk_dist else None
            realized_usd = round(realized_r * risk_usd, 2) if risk_usd else None

            portions = {
                "tp1": 0.50 if tp1 else 0,
                "tp2": 0.25 if tp2 else 0,
                "tp3": 0.25 if tp3 else 0,
            }

            patch: dict = {
                "realized_r":    round(realized_r, 3),
                "outcome_class": outcome,
                "portions_closed": portions,
            }
            if realized_pts is not None:
                patch["realized_pnl_pts"] = realized_pts
            if realized_usd is not None:
                patch["realized_pnl_usd"] = realized_usd

            sb.table("signal_history").update(patch).eq("id", row["id"]).execute()
            updated += 1
        except Exception as e:
            logger.error(f"backfill-r row {row.get('id')}: {e}")
            errors += 1

    logger.info(f"backfill-r complete: {updated} updated, {errors} errors")
    return {
        "updated": updated,
        "errors":  errors,
        "message": f"Backfilled realized_r for {updated} closed signals. Re-fetch /signal-history/stats to see updated avg_r / expectancy.",
    }


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
