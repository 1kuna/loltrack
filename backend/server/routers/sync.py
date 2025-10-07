from __future__ import annotations

from typing import Optional
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from ..deps import config as get_cfg
from core.store import Store
from core.metrics import ingest_and_compute_recent
from core.riot import RiotClient
from core.windows import rebuild_windows
from core.gis import process_new_matches
from core.metrics_extras import compute_extras
from ..ingest.ddragon import ensure_ddragon, load_items_json
from core.live import LiveClient


router = APIRouter()


@router.post("/pull")
def pull(since: Optional[str] = Query(None), count: int = Query(20), queue: Optional[int] = Query(None)):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "no_puuid", "message": "Set Riot ID first"}}
    store = Store()
    rc = RiotClient.from_config(cfg, kind="bg")
    import time, logging
    t0 = time.time()
    n = ingest_and_compute_recent(rc, store, puuid, since=since, count=count, queue_filter=queue)
    rebuild_windows(store, cfg)
    # Compute GIS for any new matches (chronological to respect smoothing)
    try:
        t1 = time.time()
        m = process_new_matches(store, puuid, queue_filter=queue)
        logging.getLogger(__name__).debug("pull: ingested=%s, gis_matches=%s, ingest_ms=%.1f, gis_ms=%.1f", n, m, (t1-t0)*1000, (time.time()-t1)*1000)
    except Exception:
        pass
    _kickoff_precompute_missing(puuid)
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
            rc = RiotClient.from_config(cfg, kind="bg")
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
            # Compute GIS for matches
            try:
                t2 = time.time()
                m = process_new_matches(store, puuid, queue_filter=None)
                import logging as _logging
                _logging.getLogger(__name__).debug("bootstrap: matches=%s, gis_matches=%s, gis_ms=%.1f", n_total, m, (time.time()-t2)*1000)
            except Exception:
                pass
            # Opportunistically kick precompute of any missing extras (skip if in live game)
            _kickoff_precompute_missing(puuid)
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


def _kickoff_precompute_missing(puuid: str, limit: int = 150) -> None:
    # Don't start if live game
    try:
        if LiveClient().status().startswith("in_game"):
            return
    except Exception:
        pass
    def run():
        try:
            store = Store()
            ver = ensure_ddragon()
            items = load_items_json(ver)
            with store.connect() as con:
                con.row_factory = sqlite3.Row
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
                    (puuid, limit),
                ).fetchall()
            for r in rows:
                # stop early if user starts a game
                try:
                    if LiveClient().status().startswith("in_game"):
                        return
                except Exception:
                    pass
                import json as _json
                match = _json.loads(r["raw_json"]) if r["raw_json"] else {}
                timeline = _json.loads(r["timeline_raw"]) if r["timeline_raw"] else {"info": {"frames": []}}
                computed = compute_extras(match, timeline, items, puuid)
                store.upsert_metrics_extras(r["match_id"], {"match_id": r["match_id"], **computed["extras_row"]})
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


# Precompute advanced metrics for existing matches (background)
_PRECOMP_TASKS = {}


@router.post("/precompute-extras")
def precompute_extras(limit: int = Query(100), force: bool = Query(False)):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot ID in Settings."}}
    # Guard: do not run while in live match
    try:
        if LiveClient().status().startswith("in_game"):
            return {"ok": False, "error": {"code": "IN_GAME", "message": "Currently in a live match. Try again later."}}
    except Exception:
        pass
    task_id = f"precomp-{int(time.time())}"
    _PRECOMP_TASKS[task_id] = {"phase": "queued", "progress": 0.0, "detail": ""}

    def run():
        try:
            store = Store()
            ver = ensure_ddragon()
            items = load_items_json(ver)
            with store.connect() as con:
                con.row_factory = sqlite3.Row
                base_sql = (
                    "SELECT m.match_id, m.raw_json, t.raw_json as timeline_raw "
                    "FROM matches m "
                    "LEFT JOIN metrics_extras ex ON ex.match_id = m.match_id "
                    "LEFT JOIN timelines t ON t.match_id = m.match_id "
                    "WHERE m.puuid=? "
                )
                if not force:
                    base_sql += "AND ex.match_id IS NULL "
                base_sql += "ORDER BY m.game_creation_ms DESC LIMIT ?"
                rows = con.execute(base_sql, (puuid, limit)).fetchall()
            n = len(rows)
            done = 0
            for r in rows:
                # Check early whether live state changed; abort if so
                try:
                    if LiveClient().status().startswith("in_game"):
                        _PRECOMP_TASKS[task_id] = {"phase": "stopped", "progress": done/max(n,1), "detail": "IN_GAME"}
                        return
                except Exception:
                    pass
                import json as _json
                match = _json.loads(r["raw_json"]) if r["raw_json"] else {}
                timeline = _json.loads(r["timeline_raw"]) if r["timeline_raw"] else {"info": {"frames": []}}
                computed = compute_extras(match, timeline, items, puuid)
                store.upsert_metrics_extras(r["match_id"], {"match_id": r["match_id"], **computed["extras_row"]})
                done += 1
                _PRECOMP_TASKS[task_id] = {"phase": "running", "progress": done / max(n, 1), "detail": f"{done}/{n}"}
            _PRECOMP_TASKS[task_id] = {"phase": "done", "progress": 1.0, "detail": f"{done}/{n}"}
        except Exception as e:
            _PRECOMP_TASKS[task_id] = {"phase": "error", "progress": 1.0, "detail": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True, "data": {"task_id": task_id}}


@router.get("/precompute-status")
def precompute_status(id: str):
    s = _PRECOMP_TASKS.get(id)
    if not s:
        return {"ok": False, "error": {"code": "not_found", "message": "unknown task"}}
    return {"ok": True, "data": s}
