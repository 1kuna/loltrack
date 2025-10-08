from __future__ import annotations

from typing import Any, Dict, Optional, List
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from core.store import Store
from ..deps import config as get_cfg
from ..ingest.ddragon import ensure_ddragon, champ_id_to_name, load_items_json
from core.metrics_extras import compute_extras


router = APIRouter()


@router.get("/matches")
def list_matches(
    limit: int = Query(50),
    offset: int = Query(0),
    queue: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    champion: Optional[int] = Query(None),
    patch: Optional[str] = Query(None),
):
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        q = (
            "SELECT m.match_id, m.puuid, m.queue_id, m.game_creation_ms, m.game_duration_s, m.patch, m.role, m.champion_id, m.raw_json, "
            "x.cs10, x.gd10, x.xpd10, x.dl14, ex.dpm as dpm_cached, ex.vision_per_min as vpm_cached, ex.obj_participation as objp_cached "
            "FROM matches m LEFT JOIN metrics x ON x.match_id = m.match_id "
            "LEFT JOIN metrics_extras ex ON ex.match_id = m.match_id"
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
        q += " ORDER BY m.game_creation_ms DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)
        cur = con.execute(q, params)
        rows = cur.fetchall()
        # Preload inst_contrib for these matches to build domain-based badges
        match_ids = [r["match_id"] for r in rows]
        ic_map: Dict[str, Dict[str, float]] = {}
        if match_ids:
            # SQLite parameter placeholders
            ph = ",".join(["?"] * len(match_ids))
            ic_rows = con.execute(
                f"SELECT match_id, domain, inst_score, z_metrics FROM inst_contrib WHERE match_id IN ({ph})",
                match_ids,
            ).fetchall()
            for ir in ic_rows:
                ic_map.setdefault(ir["match_id"], {}).setdefault(ir["domain"], {})
                ent = ic_map[ir["match_id"]][ir["domain"]]
                ent["inst"] = float(ir["inst_score"]) if ir["inst_score"] is not None else 50.0
                ent["z"] = ir["z_metrics"]
    import json as _json
    data: List[Dict[str, Any]] = []
    for r in rows:
        base = {
            "match_id": r["match_id"],
            "queue_id": r["queue_id"],
            "game_creation_ms": r["game_creation_ms"],
            "game_duration_s": r["game_duration_s"],
            "patch": r["patch"],
            "role": r["role"],
            "champion_id": r["champion_id"],
            "cs10": r["cs10"],
            "gd10": r["gd10"],
            "xpd10": r["xpd10"],
            "dl14": r["dl14"],
        }
        try:
            m = _json.loads(r["raw_json"]) if r["raw_json"] else {}
            parts = m.get("info", {}).get("participants", [])
            me = next((p for p in parts if p.get("puuid") == r["puuid"]), None)
            if me:
                duration_s = int((m.get("info", {}).get("gameDuration") or 0)) or max(1, int(r["game_duration_s"] or 0))
                minutes = max(1.0, duration_s / 60.0)
                cs_total = int((me.get("totalMinionsKilled") or 0) + (me.get("neutralMinionsKilled") or 0))
                team_kills = sum(int(p.get("kills") or 0) for p in parts if int(p.get("teamId") or 0) == int(me.get("teamId") or 0)) or 0
                kp = ((int(me.get("kills") or 0) + int(me.get("assists") or 0)) / team_kills * 100.0) if team_kills > 0 else 0.0
                dpm = float(r["dpm_cached"]) if r["dpm_cached"] is not None else float(me.get("totalDamageDealtToChampions") or 0) / minutes
                vpm = float(r["vpm_cached"]) if r["vpm_cached"] is not None else float(me.get("visionScore") or 0) / minutes
                # Build badges from domain inst contributions if available
                domain_badges: List[str] = []
                try:
                    dmap = ic_map.get(r["match_id"]) or {}
                    scored: List[tuple[str, float, float]] = []
                    for d, obj in dmap.items():
                        inst = float((obj or {}).get("inst") or 50.0)
                        z = {}
                        try:
                            import json as _json
                            z = _json.loads((obj or {}).get("z") or "{}")
                        except Exception:
                            z = {}
                        zvals = [float(v) for v in (z or {}).values() if v is not None]
                        zmin = min(zvals) if zvals else 0.0
                        zmax = max(zvals) if zvals else 0.0
                        # Thresholds
                        if inst <= 45.0 and zmin <= -0.7:
                            scored.append((d, inst - 50.0, -abs(zmin)))
                        elif inst >= 55.0 and zmax >= 0.7:
                            scored.append((d, inst - 50.0, abs(zmax)))
                    # Sort by absolute inst deviation then z magnitude
                    scored.sort(key=lambda x: (abs(x[1]), abs(x[2])), reverse=True)
                    for d, dv, _ in scored[:3]:
                        domain_badges.append(f"{d.capitalize()} {'High' if dv>0 else 'Low'}")
                except Exception:
                    pass
                data.append({
                    **base,
                    "k": int(me.get("kills") or 0),
                    "d": int(me.get("deaths") or 0),
                    "a": int(me.get("assists") or 0),
                    "cs": cs_total,
                    "csm": round(cs_total / minutes, 2),
                    "gold": int(me.get("goldEarned") or 0),
                    "dmgToChamps": int(me.get("totalDamageDealtToChampions") or 0),
                    "dpm": round(dpm, 1),
                    "visionScore": int(me.get("visionScore") or 0),
                    "kp": round(kp, 1),
                    "result": "Win" if bool(me.get("win")) else "Lose",
                    "badges": (domain_badges or [])[:2] + _badges(dpm, vpm, float(r["objp_cached"]) if r["objp_cached"] is not None else None),
                })
            else:
                data.append(base)
        except Exception:
            data.append(base)
    return {"ok": True, "data": data}


def _badges(dpm: float, vpm: float, objp: Optional[float]) -> List[str]:
    out: List[str] = []
    try:
        if dpm is not None and dpm >= 600:
            out.append("High DPM")
    except Exception:
        pass
    try:
        if vpm is not None and vpm >= 1.0:
            out.append("Vision King")
    except Exception:
        pass
    try:
        if objp is not None and objp >= 60.0:
            out.append("Objective Beast")
    except Exception:
        pass
    return out


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


@router.get("/match/{match_id}/advanced")
def match_advanced(match_id: str):
    store = Store()
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        # Try cache first
        ex = con.execute("SELECT * FROM metrics_extras WHERE match_id=?", (match_id,)).fetchone()
        m = con.execute("SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
        t = con.execute("SELECT raw_json FROM timelines WHERE match_id=?", (match_id,)).fetchone()
    if not m:
        return {"ok": False, "error": {"code": "not_found", "message": "match not found"}}
    match_raw = m["raw_json"]
    import json as _json
    match = _json.loads(match_raw) if match_raw else {}
    timeline = _json.loads(t[0]) if (t and t[0]) else {"info": {"frames": []}}
    puuid = m["puuid"]

    # Load Data Dragon items for mythic detection
    ver = ensure_ddragon()
    items_json = load_items_json(ver)

    # If we have cached extras, prefer them for overview to keep response snappy
    import math as _math
    if ex:
        parts = match.get("info", {}).get("participants", [])
        me = next((p for p in parts if p.get("puuid") == puuid), None) or {}
        duration_s = int((match.get("info", {}).get("gameDuration") or 0))
        minutes = max(1.0, duration_s / 60.0)
        cs_total = int((me.get("totalMinionsKilled") or 0) + (me.get("neutralMinionsKilled") or 0))
        team_kills = sum(int(p.get("kills") or 0) for p in parts if int(p.get("teamId") or 0) == int(me.get("teamId") or 0)) or 0
        kp = ((int(me.get("kills") or 0) + int(me.get("assists") or 0)) / team_kills * 100.0) if team_kills > 0 else 0.0
        overview = {
            "k": int(me.get("kills") or 0),
            "d": int(me.get("deaths") or 0),
            "a": int(me.get("assists") or 0),
            "kda": round(((int(me.get("kills") or 0) + int(me.get("assists") or 0)) / max(1, int(me.get("deaths") or 0))), 2),
            "kp": round(kp, 1),
            "dpm": float(ex["dpm"] or 0.0),
            "gpm": float(ex["gpm"] or 0.0),
            "csm": round(cs_total / minutes, 2),
            "gd10": 0,
            "gd15": 0,
            "xpd10": 0,
            "xpd15": 0,
            "dmgObj": int(ex["dmg_obj"] or 0),
            "dmgTurrets": int(ex["dmg_turrets"] or 0),
            "visionPerMin": float(ex["vision_per_min"] or 0.0),
            "wardsPlaced": int(me.get("wardsPlaced") or 0),
            "wardsKilled": int(me.get("wardsKilled") or 0),
            "items": [],
            "mythicAtS": int(ex["mythic_at_s"] or 0) or None,
            "twoItemAtS": int(ex["two_item_at_s"] or 0) or None,
            "objParticipation": float(ex["obj_participation"] or 0.0),
            "roamDistancePre14": float(ex["roam_distance_pre14"] or 0.0),
        }
        # Fill diffs via frames quickly
        try:
            from core.metrics import find_frame_at, lane_opponent_id, MS
            pid = int((me or {}).get("participantId") or 0)
            f10 = find_frame_at(timeline, 10 * 60 * MS)
            f15 = find_frame_at(timeline, 15 * 60 * MS)
            opp = lane_opponent_id(match, timeline, pid)
            pf10 = f10.get("participantFrames", {}).get(str(pid), {})
            pf15 = f15.get("participantFrames", {}).get(str(pid), {})
            op10 = f10.get("participantFrames", {}).get(str(opp), {}) if opp else {}
            op15 = f15.get("participantFrames", {}).get(str(opp), {}) if opp else {}
            overview.update({
                "gd10": int((pf10.get("totalGold") or 0) - (op10.get("totalGold") or 0)),
                "gd15": int((pf15.get("totalGold") or 0) - (op15.get("totalGold") or 0)),
                "xpd10": int((pf10.get("xp") or 0) - (op10.get("xp") or 0)),
                "xpd15": int((pf15.get("xp") or 0) - (op15.get("xp") or 0)),
            })
        except Exception:
            pass
        # Items list from events
        try:
            items = []
            for fr in timeline.get("info", {}).get("frames", []) or []:
                for ev in fr.get("events", []) or []:
                    if ev.get("type") == "ITEM_PURCHASED" and int(ev.get("participantId") or 0) == int((me or {}).get("participantId") or 0):
                        items.append({"id": int(ev.get("itemId") or 0), "t": int(int(ev.get("timestamp") or 0) / 1000)})
            overview["items"] = sorted(items, key=lambda x: x["t"])[:50]
        except Exception:
            pass
    else:
        # Build overview using compute_extras; update cache if missing
        computed = compute_extras(match, timeline, items_json, puuid)
        overview = computed["overview"]
        row = {"match_id": match_id, **computed["extras_row"]}
        store.upsert_metrics_extras(match_id, row)
    # Add runes from participant
    try:
        parts = match.get("info", {}).get("participants", [])
        me = next((p for p in parts if p.get("puuid") == puuid), None)
        if me:
            perks = me.get("perks") or {}
            styles = perks.get("styles") or []
            primary = (styles[0].get("style") if len(styles) > 0 else None) or 0
            sub = (styles[1].get("style") if len(styles) > 1 else None) or 0
            shards = [int(perks.get("statPerks", {}).get(k) or 0) for k in ("offense", "flex", "defense")]
            overview["runes"] = {"primary": int(primary), "sub": int(sub), "shards": shards}
    except Exception:
        pass

    # Series 0–20 minutes
    def series_0_20() -> Dict[str, Any]:
        frames = timeline.get("info", {}).get("frames", []) or []
        max_min = min(20, int((match.get("info", {}).get("gameDuration") or 0) / 60))
        minutes = list(range(0, max_min + 1))
        me = next((p for p in match.get("info", {}).get("participants", []) if p.get("puuid") == puuid), None)
        pid = int((me or {}).get("participantId") or 0)
        # try importing helper for opponent
        try:
            from core.metrics import lane_opponent_id, MS
            opp = lane_opponent_id(match, timeline, pid)
            MSv = MS
        except Exception:
            opp = None
            MSv = 1000
        goldDiff: List[int] = []
        xpDiff: List[int] = []
        csAcc: List[int] = []
        for m in minutes:
            ts = m * 60 * MSv
            fr = min(frames, key=lambda f: abs(int(f.get("timestamp") or 0) - ts)) if frames else {}
            pfs = fr.get("participantFrames", {}) if fr else {}
            mef = pfs.get(str(pid), {})
            opf = pfs.get(str(opp), {}) if opp else {}
            goldDiff.append(int((mef.get("totalGold") or 0) - (opf.get("totalGold") or 0)))
            xpDiff.append(int((mef.get("xp") or 0) - (opf.get("xp") or 0)))
            csAcc.append(int((mef.get("minionsKilled") or 0) + (mef.get("jungleMinionsKilled") or 0)))
        return {"minutes": minutes, "goldDiff": goldDiff, "xpDiff": xpDiff, "cs": csAcc}

    series = series_0_20()

    # Event slices up to 20m
    events = {"elite": [], "buildings": [], "kills": [], "wards": [], "items": []}
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            ts = int(ev.get("timestamp") or 0)
            if ts > 20 * 60 * 1000:
                continue
            typ = ev.get("type")
            if typ == "ELITE_MONSTER_KILL":
                events["elite"].append({
                    "t": ts // 1000,
                    "monsterType": ev.get("monsterType"),
                    "killerId": ev.get("killerId"),
                    "assists": ev.get("assistingParticipantIds") or [],
                })
            elif typ == "BUILDING_KILL":
                events["buildings"].append({
                    "t": ts // 1000,
                    "buildingType": ev.get("buildingType"),
                    "towerType": ev.get("towerType"),
                    "killerId": ev.get("killerId"),
                })
            elif typ == "CHAMPION_KILL":
                events["kills"].append({
                    "t": ts // 1000,
                    "killerId": ev.get("killerId"),
                    "victimId": ev.get("victimId"),
                    "assists": ev.get("assistingParticipantIds") or [],
                })
            elif typ in ("WARD_PLACED", "WARD_KILL"):
                events["wards"].append({
                    "t": ts // 1000,
                    "type": typ,
                    "wardType": ev.get("wardType"),
                    "creatorId": ev.get("creatorId"),
                    "killerId": ev.get("killerId"),
                })
            elif typ == "ITEM_PURCHASED":
                events["items"].append({
                    "t": ts // 1000,
                    "participantId": ev.get("participantId"),
                    "itemId": ev.get("itemId"),
                })

    return {"ok": True, "data": {"overview": overview, "series": series, "events": events}}


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
        ps = con.execute(
            "SELECT patch as id, COUNT(*) as n, MAX(game_creation_ms) as last_ms FROM metrics WHERE puuid=? GROUP BY patch ORDER BY last_ms DESC",
            (puuid,),
        ).fetchall()
    queues = [{"id": int(r["id"]) if r["id"] is not None else None, "count": int(r["n"]) } for r in qs]
    roles = [{"id": (r["id"] or ""), "count": int(r["n"]) } for r in rs if r["id"]]
    patches = [{"id": (r["id"] or ""), "count": int(r["n"]) } for r in ps if r["id"]]
    return {"ok": True, "data": {"queues": queues, "roles": roles, "patches": patches}}
