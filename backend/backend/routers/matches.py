from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from loltrack.store import Store


router = APIRouter()


@router.get("/matches")
def list_matches(limit: int = Query(50), queue: Optional[int] = Query(None)):
    store = Store()
    with store.connect() as con:
        q = "SELECT match_id, puuid, queue_id, game_creation_ms, game_duration_s, patch, role, champion_id FROM matches"
        params: list[Any] = []
        if queue is not None:
            q += " WHERE queue_id=?"
            params.append(queue)
        q += " ORDER BY game_creation_ms DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(q, params).fetchall()
    return {"ok": True, "data": [dict(r) for r in rows]}


@router.get("/match/{match_id}")
def match_detail(match_id: str):
    store = Store()
    with store.connect() as con:
        m = con.execute("SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
        t = con.execute("SELECT raw_json FROM timelines WHERE match_id=?", (match_id,)).fetchone()
    if not m:
        return {"ok": False, "error": {"code": "not_found", "message": "match not found"}}
    out = dict(m)
    out["timeline_raw"] = t[0] if t else None
    return {"ok": True, "data": out}
