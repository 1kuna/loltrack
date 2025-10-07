from __future__ import annotations

from typing import Any, Dict, Optional
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from loltrack.store import Store
from ..deps import config as get_cfg
from ..ingest.ddragon import ensure_ddragon, champ_id_to_name


router = APIRouter()


@router.get("/matches")
def list_matches(
    limit: int = Query(50),
    queue: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    champion: Optional[int] = Query(None),
    patch: Optional[str] = Query(None),
):
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        q = (
            "SELECT m.match_id, m.puuid, m.queue_id, m.game_creation_ms, m.game_duration_s, m.patch, m.role, m.champion_id, "
            "x.cs10, x.gd10, x.xpd10, x.dl14 "
            "FROM matches m LEFT JOIN metrics x ON x.match_id = m.match_id"
        )
        where: list[str] = []
        params: list[Any] = []
        if queue is not None and queue != -1:
            where.append("m.queue_id=?")
            params.append(queue)
        if role is not None and role != "":
            where.append("m.role=?")
            params.append(role)
        if champion is not None:
            where.append("m.champion_id=?")
            params.append(champion)
        if patch is not None and patch != "":
            where.append("m.patch=?")
            params.append(patch)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY m.game_creation_ms DESC LIMIT ?"
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


@router.get("/matches/recent-champions")
def recent_champions(limit: int = Query(25), queue: Optional[int] = Query(None)):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": True, "data": []}
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        q = (
            "SELECT champion_id as id, COUNT(*) as n, MAX(game_creation_ms) as last_ms "
            "FROM metrics WHERE puuid=?"
        )
        params: list[Any] = [puuid]
        if queue is not None and queue != -1:
            q += " AND queue_id=?"
            params.append(queue)
        q += " GROUP BY champion_id ORDER BY last_ms DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(q, params).fetchall()
    ver = ensure_ddragon()
    out = []
    for r in rows:
        cid = int(r["id"]) if r["id"] is not None else 0
        name = champ_id_to_name(ver, cid) or str(cid)
        out.append({"id": cid, "name": name, "count": int(r["n"]), "last_ms": int(r["last_ms"]) if r["last_ms"] else 0})
    return {"ok": True, "data": out}


@router.get("/matches/segments")
def segments(queue: Optional[int] = Query(None)):
    """Return played queues and roles for the current player (optionally scoped by queue for roles)."""
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": True, "data": {"queues": [], "roles": []}}
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        qs = con.execute(
            "SELECT queue_id as id, COUNT(*) as n, MAX(game_creation_ms) as last_ms FROM metrics WHERE puuid=? GROUP BY queue_id ORDER BY last_ms DESC",
            (puuid,),
        ).fetchall()
        params: list[Any] = [puuid]
        q = "SELECT role as id, COUNT(*) as n FROM metrics WHERE puuid=?"
        if queue is not None and queue != -1:
            q += " AND queue_id=?"
            params.append(queue)
        q += " GROUP BY role ORDER BY n DESC"
        rs = con.execute(q, params).fetchall()
    queues = [{"id": int(r["id"]) if r["id"] is not None else None, "count": int(r["n"]) } for r in qs]
    roles = [{"id": (r["id"] or ""), "count": int(r["n"]) } for r in rs if r["id"]]
    return {"ok": True, "data": {"queues": queues, "roles": roles}}
