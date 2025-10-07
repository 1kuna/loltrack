from __future__ import annotations

import json
import asyncio
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .poller import stream_live_payloads
import threading
from ..deps import config as get_cfg
from core.store import Store
from core.metrics import ingest_and_compute_recent
from core.riot import RiotClient
from core.windows import rebuild_windows


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
        # On live end, kick a light background ingest for freshness
        def _post_live():
            try:
                cfg = get_cfg()
                puuid = (cfg.get("player", {}) or {}).get("puuid")
                if not puuid:
                    return
                store = Store()
                try:
                    rc = RiotClient.from_config(cfg, kind="bg")
                except Exception:
                    return
                n = ingest_and_compute_recent(rc, store, puuid, since="2h", count=5, queue_filter=None)
                if n > 0:
                    rebuild_windows(store, cfg)
            except Exception:
                pass
        threading.Thread(target=_post_live, daemon=True).start()


def register_ws(app: FastAPI) -> None:
    app.websocket("/ws/live")(ws_live_endpoint)
