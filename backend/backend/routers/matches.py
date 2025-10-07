from __future__ import annotations

from typing import Any, Dict, Optional
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from loltrack.store import Store


router = APIRouter()


@router.get("/matches")
def list_matches(limit: int = Query(50), queue: Optional[int] = Query(None)):
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        q = "SELECT match_id, puuid, queue_id, game_creation_ms, game_duration_s, patch, role, champion_id FROM matches"
        params: list[Any] = []
        if queue is not None:
            q += " WHERE queue_id=?"
            params.append(queue)
        q += " ORDER BY game_creation_ms DESC LIMIT ?"
        params.append(limit)
        cur = con.execute(q, params)
        rows = cur.fetchall()
    data = [{k: r[k] for k in r.keys()} for r in rows]
    return {"ok": True, "data": data}


@router.get("/match/{match_id}")
def match_detail(match_id: str):
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        m = con.execute("SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
        t = con.execute("SELECT raw_json FROM timelines WHERE match_id=?", (match_id,)).fetchone()
    if not m:
        return {"ok": False, "error": {"code": "not_found", "message": "match not found"}}
    out = {k: m[k] for k in m.keys()}
    out["timeline_raw"] = t[0] if t else None
    return {"ok": True, "data": out}
