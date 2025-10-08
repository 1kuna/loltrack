from __future__ import annotations

import json
import threading
import time
from typing import Any

from core.store import Store
from core.metrics_extras import compute_extras
from ..deps import config as get_cfg
from ..ingest.ddragon import ensure_ddragon, load_items_json
from core.live import LiveClient


_STARTED = False
_INTERVAL_SEC = 3600  # 1 hour
_MAX_PER_SWEEP = 60   # keep CPU usage low per cycle


def start_sweeper() -> None:
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    th = threading.Thread(target=_loop, daemon=True)
    th.start()


def _loop():
    # initial small delay to avoid competing with startup tasks
    time.sleep(15)
    while True:
        try:
            _run_once()
        except Exception:
            # swallow; try again next cycle
            pass
        # sleep a full interval between sweeps
        time.sleep(_INTERVAL_SEC)


def _run_once():
    cfg = get_cfg()
    puuid = (cfg.get("player", {}) or {}).get("puuid")
    if not puuid:
        return
    # Do not run while in a live game
    try:
        if LiveClient().status().startswith("in_game"):
            return
    except Exception:
        pass

    store = Store()
    ver = ensure_ddragon()
    items = load_items_json(ver)
    # Fetch a small batch of most recent matches missing extras
    with store.connect() as con:
        con.row_factory = __import__("sqlite3").Row
        rows = con.execute(
            """
            SELECT m.match_id, m.raw_json, t.raw_json as timeline_raw
            FROM matches m
            LEFT JOIN metrics_extras ex ON ex.match_id = m.match_id
            LEFT JOIN timelines t ON t.match_id = m.match_id
            WHERE m.puuid=? AND ex.match_id IS NULL
            ORDER BY m.game_creation_ms DESC
            LIMIT ?
            """,
            (puuid, _MAX_PER_SWEEP),
        ).fetchall()
    if not rows:
        return
    # Light-touch compute with small sleeps to minimize CPU spikes
    for r in rows:
        try:
            # Re-check live state between items
            try:
                if LiveClient().status().startswith("in_game"):
                    return
            except Exception:
                pass
            match = json.loads(r["raw_json"]) if r["raw_json"] else {}
            timeline = json.loads(r["timeline_raw"]) if r["timeline_raw"] else {"info": {"frames": []}}
            computed = compute_extras(match, timeline, items, puuid)
            store.upsert_metrics_extras(r["match_id"], {"match_id": r["match_id"], **computed["extras_row"]})
        except Exception:
            # continue with next
            pass
        # Short sleep to yield CPU and avoid bursts
        time.sleep(0.01)
