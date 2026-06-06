# backend/routers/forecast.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from services.supabase_service import get_latest_forecast, get_forecast_history
from services.redis_service import cache_get
from services.websocket_manager import ws_manager
from datetime import datetime
import logging

router = APIRouter(prefix="/forecast", tags=["forecast"])
logger = logging.getLogger(__name__)


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
