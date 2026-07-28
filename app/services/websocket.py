"""
WebSocket manager — broadcasts real-time recovery events to the frontend.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
import asyncio
import json

router = APIRouter()

# trip_id → list of connected websockets
_connections: Dict[int, List[WebSocket]] = {}

# Reference to the main event loop — captured on first WS connect.
# Background threads use this to schedule sends via run_coroutine_threadsafe.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


@router.websocket("/ws/{trip_id}")
async def websocket_endpoint(websocket: WebSocket, trip_id: int):
    global _main_loop
    _main_loop = asyncio.get_event_loop()

    await websocket.accept()
    _connections.setdefault(trip_id, []).append(websocket)
    try:
        await websocket.send_text(json.dumps({"event": "CONNECTED", "trip_id": trip_id}))
        while True:
            await websocket.receive_text()   # keep connection alive
    except WebSocketDisconnect:
        if trip_id in _connections:
            _connections[trip_id] = [ws for ws in _connections[trip_id] if ws != websocket]


def broadcast(trip_id: int, payload: dict):
    """
    Synchronous broadcast — called from background tasks/threads.
    Schedules sends on the main event loop via run_coroutine_threadsafe.
    """
    message = json.dumps(payload)
    connections = _connections.get(trip_id, [])
    if not connections or _main_loop is None:
        return

    dead = []
    for ws in connections:
        try:
            future = asyncio.run_coroutine_threadsafe(ws.send_text(message), _main_loop)
            future.result(timeout=5)
        except Exception:
            dead.append(ws)

    for ws in dead:
        try:
            connections.remove(ws)
        except ValueError:
            pass
