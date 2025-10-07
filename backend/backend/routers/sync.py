from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..deps import config as get_cfg
from loltrack.store import Store
from loltrack.metrics import ingest_and_compute_recent
from loltrack.riot import RiotClient
from loltrack.windows import rebuild_windows


router = APIRouter()


@router.post("/pull")
def pull(since: Optional[str] = Query(None), count: int = Query(20), queue: Optional[int] = Query(None)):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "no_puuid", "message": "Set Riot ID first"}}
    store = Store()
    rc = RiotClient.from_config(cfg)
    n = ingest_and_compute_recent(rc, store, puuid, since=since, count=count, queue_filter=queue)
    rebuild_windows(store, cfg)
    return {"ok": True, "data": {"ingested": n}}

# Bootstrap + status (background)
import threading, time
from ..ingest.ddragon import ensure_ddragon

_BOOT_TASKS = {}


@router.post("/bootstrap")
def bootstrap():
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    # Pre-validate: API key + puuid required
    try:
        rc = RiotClient.from_config(cfg)
        if not rc.verify_key() or not puuid:
            return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot API key and Riot ID in Settings."}}
    except Exception:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot API key and Riot ID in Settings."}}
    task_id = f"boot-{int(time.time())}"
    _BOOT_TASKS[task_id] = {"phase": "queued", "progress": 0.0, "detail": ""}

    def run():
        try:
            _BOOT_TASKS[task_id] = {"phase": "ddragon", "progress": 0.1, "detail": "caching assets"}
            ensure_ddragon()
            _BOOT_TASKS[task_id] = {"phase": "match_ids", "progress": 0.2, "detail": "fetching ids"}
            store = Store()
            rc = RiotClient.from_config(cfg)
            # ingest last 14d or 20 matches
            try:
                n_total = ingest_and_compute_recent(rc, store, puuid, since="14d", count=50, queue_filter=None)
            except Exception as e:
                # Map rate limit
                msg = str(e)
                if "429" in msg:
                    _BOOT_TASKS[task_id] = {"phase": "error", "progress": 1.0, "detail": "RIOT_429"}
                    return
                _BOOT_TASKS[task_id] = {"phase": "error", "progress": 1.0, "detail": "INGEST_ERROR"}
                return
            _BOOT_TASKS[task_id] = {"phase": "computing", "progress": 0.9, "detail": f"{n_total} matches"}
            rebuild_windows(store, cfg)
            _BOOT_TASKS[task_id] = {"phase": "done", "progress": 1.0, "detail": f"{n_total} matches"}
        except Exception as e:
            _BOOT_TASKS[task_id] = {"phase": "error", "progress": 1.0, "detail": "INGEST_ERROR"}

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True, "data": {"task_id": task_id}}


@router.get("/status")
def status(id: str):
    s = _BOOT_TASKS.get(id)
    if not s:
        return {"ok": False, "error": {"code": "not_found", "message": "unknown task"}}
    return {"ok": True, "data": s}
