"""
WebSocket manager — broadcasts real-time recovery events to the frontend.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

router = APIRouter()

# trip_id → list of connected websockets
_connections: Dict[int, List[WebSocket]] = {}


@router.websocket("/ws/{trip_id}")
async def websocket_endpoint(websocket: WebSocket, trip_id: int):
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
    Synchronous broadcast — called from background tasks.
    Uses send_sync pattern via the WebSocket's underlying transport.
    """
    import asyncio
    message = json.dumps(payload)
    connections = _connections.get(trip_id, [])
    dead = []
    for ws in connections:
        try:
            # Run async send in a new event loop if called from a thread
            loop = asyncio.new_event_loop()
            loop.run_until_complete(ws.send_text(message))
            loop.close()
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)
