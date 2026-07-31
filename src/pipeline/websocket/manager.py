# -*- coding: utf-8 -*-
"""
WebSocket Connection Manager
----------------------------
Manages live WebSocket clients and broadcasts real-time progress events
(uploading, queued, embedding_completed, drive_completed, failure, retries) to the Next.js UI.
"""

import json
import logging
from typing import Dict, List, Any
from fastapi import WebSocket

logger = logging.getLogger("pipeline.websocket")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket client connected: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket client disconnected: {client_id}")

    async def send_event(self, client_id: str, event_type: str, data: Dict[str, Any]):
        """Sends an event payload to a specific connected client."""
        if client_id in self.active_connections:
            try:
                message = json.dumps({"event": event_type, "data": data})
                await self.active_connections[client_id].send_text(message)
            except Exception as e:
                logger.warning(f"Error sending WebSocket message to {client_id}: {e}")
                self.disconnect(client_id)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcasts an event payload to all connected clients."""
        if not self.active_connections:
            return

        message = json.dumps({"event": event_type, "data": data})
        disconnected = []

        for client_id, connection in list(self.active_connections.items()):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed broadcasting to client {client_id}: {e}")
                disconnected.append(client_id)

    async def send_recognition_progress(self, session_id: str, stage: str, message: str, payload: Dict[str, Any] = None):
        """Sends real-time recognition pipeline stage progress to client WebSocket."""
        data = {
            "stage": stage,
            "message": message,
            "payload": payload or {}
        }
        await self.send_event(session_id, "recognition_progress", data)

    async def close_session(self, session_id: str, reason: str = "Completed"):
        """Gracefully closes a completed or idle recognition session WebSocket connection."""
        if session_id in self.active_connections:
            ws = self.active_connections[session_id]
            try:
                await ws.send_json({"event": "recognition_complete", "reason": reason})
                await ws.close()
            except Exception:
                pass
            finally:
                self.disconnect(session_id)


ws_manager = ConnectionManager()

