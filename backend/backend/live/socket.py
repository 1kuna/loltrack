from __future__ import annotations

import json
import asyncio
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .poller import stream_live_payloads


async def ws_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_hb = time.time()
    try:
        for payload in stream_live_payloads():
            now = time.time()
            await websocket.send_text(json.dumps(payload))
            if now - last_hb >= 5:
                await websocket.send_text(json.dumps({"event": "hb"}))
                last_hb = now
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.send_text(json.dumps({"event": "live_end"}))
        except Exception:
            pass


def register_ws(app: FastAPI) -> None:
    app.websocket("/ws/live")(ws_live_endpoint)
