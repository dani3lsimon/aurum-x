# backend/services/websocket_manager.py
from fastapi import WebSocket
from typing import List
import json
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        data = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                dead.append(connection)
        for conn in dead:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def send_forecast_update(self, forecast: dict):
        await self.broadcast({"type": "forecast_update", "data": forecast})

    async def send_agent_update(self, agent_name: str, score: float, rationale: str):
        await self.broadcast({
            "type": "agent_update",
            "data": {"agent": agent_name, "score": score, "rationale": rationale}
        })

    async def send_alert(self, alert: dict):
        await self.broadcast({"type": "alert", "data": alert})

    async def send_regime_change(self, new_regime: str, old_regime: str, confidence: float):
        await self.broadcast({
            "type": "regime_change",
            "data": {
                "new_regime": new_regime,
                "old_regime": old_regime,
                "confidence": confidence
            }
        })

    async def send_release_alert(self, release: dict):
        await self.broadcast({"type": "release_alert", "data": release})


ws_manager = WebSocketManager()
