from __future__ import annotations

from typing import Any, Dict, Optional, List
import json

from fastapi import APIRouter, Query
import logging, time

from ..deps import config as get_cfg
from core.store import Store
from core.gis import ROLE_DOMAIN_WEIGHTS, DOMAINS, achilles_and_secondary, load_role_weights
from core import gis as _gis
from core.windows import rebuild_windows as _rebuild_windows


router = APIRouter()


@router.get("/gis/summary")
def gis_summary(queue: Optional[int] = Query(None), role: Optional[str] = Query(None)):
    t0 = time.time()
    logger = logging.getLogger(__name__)
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": True, "data": {"schema_version": "gis.v1", "context": {"queue": None, "role": None}, "overall": 50.0, "domains": {}, "delta5": 0.0, "focus": {"primary": None, "secondary": []}}}
    store = Store()
    # Treat -1 as any queue (None)
    q_in = queue if queue is not None else (cfg.get("player", {}).get("track_queues") or [None])[0]
    q = None if q_in == -1 else q_in
    # Read smoothed overall (fallback to configured queue if Any)
    cfg_queue = (cfg.get("player", {}).get("track_queues") or [None])[0]
    # Auto-detect role if not provided: dominant over last 10 ranked SR matches in context
    resolved_role = role
    try:
        if not resolved_role:
            ranked = set(int(x) for x in (cfg.get("gis", {}).get("rankedQueues") or [420, 440]))
            with store.connect() as con:
                con.row_factory = __import__('sqlite3').Row
                inner = "SELECT role FROM matches WHERE puuid=? AND queue_id IN (%s)" % (",".join([str(x) for x in ranked]))
                params = [puuid]
                if q is not None:
                    inner += " AND queue_id=?"
                    params.append(q)
                inner += " ORDER BY game_creation_ms DESC LIMIT 10"
                sql = f"SELECT role, COUNT(1) as n FROM ({inner}) t GROUP BY role ORDER BY n DESC LIMIT 1"
                row = con.execute(sql, params).fetchone()
                if row and row["role"]:
                    resolved_role = row["role"]
    except Exception:
        pass
    q_for_overall = q if q is not None else cfg_queue
    overall = store.load_overall_score(puuid, q_for_overall, resolved_role) or 50.0
    # Domain smoothed values
    domains = {d: (store.load_domain_score(puuid, q_for_overall, role, d) or 50.0) for d in DOMAINS}
    # Delta vs last 5 matches: compute inst overall average of last 5 minus previous 5
    with store.connect() as con:
        con.row_factory = __import__('sqlite3').Row
        rows = con.execute(
            """
            SELECT i.match_id, i.domain, i.inst_score, i.z_metrics, m.game_creation_ms
            FROM inst_contrib i
            JOIN matches m ON m.match_id = i.match_id
            WHERE i.puuid=? AND (? IS NULL OR m.queue_id=?) AND (? IS NULL OR m.role=?)
            ORDER BY m.game_creation_ms DESC
            LIMIT 100
            """,
            (puuid, q, q, resolved_role, resolved_role),
        ).fetchall()
    by_match: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        by_match.setdefault(r["match_id"], {"ms": int(r["game_creation_ms"] or 0), "domains": {}, "z": {}})["domains"][r["domain"]] = float(r["inst_score"])
        try:
            z = json.loads(r["z_metrics"]) if r["z_metrics"] else {}
            by_match[r["match_id"]]["z"][r["domain"]] = z
        except Exception:
            pass
    ordered = sorted(by_match.values(), key=lambda x: x["ms"], reverse=True)
    def inst_overall(dom_map: Dict[str, float]) -> float:
        role_key = (resolved_role or "").upper()
        # Prefer file-backed weights with Balanced fallback
        try:
            W_all = load_role_weights()
            W = W_all.get(role_key) or W_all.get("BALANCED") or ROLE_DOMAIN_WEIGHTS.get("UTILITY")
        except Exception:
            W = ROLE_DOMAIN_WEIGHTS.get("UTILITY")
        total = sum(W.values()) or 1.0
        s = 50.0
        for d, wk in W.items():
            if d in dom_map:
                s += (wk / total) * (dom_map[d] - 50.0)
        return s
    inst_scores = [inst_overall(x["domains"]) for x in ordered]
    last5 = inst_scores[:5]
    prev5 = inst_scores[5:10]
    def avg(arr: List[float]) -> float:
        return (sum(arr) / len(arr)) if arr else 0.0
    delta5 = round(avg(last5) - avg(prev5), 2)
    # Confidence band: recent std dev of inst overall (0..100)
    import math
    def stdev(arr: List[float]) -> float:
        if not arr:
            return 0.0
        mu = avg(arr)
        return math.sqrt(avg([(x-mu)**2 for x in arr]))
    band = round(stdev(inst_scores[:10]), 2)

    # Calibration & gating
    gis_cfg = cfg.get("gis", {})
    min_gis = int(gis_cfg.get("minMatchesForGIS", 5))
    min_focus = int(gis_cfg.get("minMatchesForFocus", 8))
    max_band = float(gis_cfg.get("maxBandForFocus", 6.0))
    min_primary_gap = float(gis_cfg.get("minPrimaryGap", -4.0))
    min_primary_lead = float(gis_cfg.get("minPrimaryLead", 2.0))
    hysteresis_matches = int(gis_cfg.get("hysteresisMatches", 3))
    ranked_queues = set(int(x) for x in (gis_cfg.get("rankedQueues") or [420, 440]))
    # Count ranked SR matches for current (queue, role)
    with store.connect() as con:
        q_sql = "SELECT COUNT(1) FROM matches WHERE puuid=? AND queue_id IN (%s)" % (",".join([str(x) for x in ranked_queues]))
        params: list[Any] = [puuid]
        if q is not None:
            q_sql += " AND queue_id=?"
            params.append(q)
        if role:
            q_sql += " AND role=?"
            params.append(role)
        ranked_sr_sample_count = int(con.execute(q_sql, params).fetchone()[0])

    # Stage 0/1/2
    if ranked_sr_sample_count < min_gis:
        calibration_stage = 0
        gis_visible = False
    elif ranked_sr_sample_count < min_focus:
        calibration_stage = 1
        gis_visible = True
    else:
        calibration_stage = 2
        gis_visible = True

    # Focus determination
    gis_cfg = cfg.get("gis", {})
    ranked_queues = gis_cfg.get("rankedQueues") or [420, 440]
    focus = achilles_and_secondary(store, puuid, q, resolved_role, last_n=8, ranked_queues=list(ranked_queues))

    # Eligibility flags
    # Determine candidate primary domain and stats for debug/eligibility
    deficits = focus.get("deficits") if isinstance(focus, dict) else {}
    # Get primary and second deficits from EWMA map
    primary_domain = None
    primary_deficit = 0.0
    second_deficit = 0.0
    lead_over_second = 0.0
    try:
        ordered_defs = sorted(deficits.items(), key=lambda kv: kv[1]) if deficits else []
        if ordered_defs:
            primary_domain, primary_deficit = ordered_defs[0]
            if len(ordered_defs) > 1:
                second_deficit = ordered_defs[1][1]
                lead_over_second = round(second_deficit - primary_deficit, 2)
    except Exception:
        pass
    # Streak check using latest matches (ordered list we already built)
    streak = 0
    if primary_domain:
        for row in ordered:
            doms = row.get("domains", {})
            if primary_domain not in doms:
                break
            # build per-match deficits
            defs = {d: (v - 50.0) for d, v in doms.items()}
            ls = sorted(defs.items(), key=lambda kv: kv[1])  # most negative first
            if not ls:
                break
            first = ls[0]
            second = ls[1] if len(ls) > 1 else (None, 0.0)
            if first[0] == primary_domain and (second[1] - first[1]) >= min_primary_lead:
                streak += 1
            else:
                break
    achilles_eligible = (calibration_stage == 2) and (band <= max_band) and (primary_domain is not None) and (primary_deficit <= min_primary_gap) and (streak >= hysteresis_matches)
    secondary_eligible = (calibration_stage == 2)

    # Advice for primary: find most negative recent z-metric within that domain
    advice: Optional[str] = None
    try:
        prim = focus.get("primary") if isinstance(focus, dict) else None
        if prim:
            # Aggregate z per metric for that domain across latest ~8 matches
            from collections import defaultdict
            acc: Dict[str, List[float]] = defaultdict(list)
            for row in ordered:
                z = (row.get("z") or {}).get(prim) if isinstance(row, dict) else None
                if not z: continue
                for k,v in z.items():
                    try: acc[k].append(float(v))
                    except: pass
            avg = {k: (sum(vs)/len(vs)) for k,vs in acc.items() if vs}
            if avg:
                worst = sorted(avg.items(), key=lambda x: x[1])[0]
                advice = suggestion_for(prim, worst[0])
    except Exception:
        advice = None
    # Apply gating to focus surface if not eligible
    if isinstance(focus, dict):
        # Override primary with candidate only if eligible
        focus["advice"] = advice if achilles_eligible else None
        focus["primary"] = primary_domain if achilles_eligible else None
        if not secondary_eligible:
            focus["secondary"] = []

    logger.debug("/gis/summary puuid=%s ctx=(%s,%s) stage=%s band=%.2f time=%.1fms", puuid, str(q_for_overall), str(resolved_role), calibration_stage, band, (time.time()-t0)*1000)
    return {"ok": True, "data": {
        "schema_version": "gis.v1",
        "context": {"queue": q_for_overall, "role": resolved_role},
        "overall": round(overall, 2),
        "domains": {k: round(v, 2) for k, v in domains.items()},
        "delta5": delta5,
        "confidence_band": band,
        "ranked_sr_sample_count": ranked_sr_sample_count,
        "calibration_stage": calibration_stage,
        "gis_visible": gis_visible,
        "achilles_eligible": achilles_eligible,
        "secondary_eligible": secondary_eligible,
        "focus_debug": {
            "primary_domain": (primary_domain.capitalize() if primary_domain else None),
            "primary_deficit": round(primary_deficit, 2) if primary_domain else None,
            "second_deficit": round(second_deficit, 2) if primary_domain else None,
            "lead_over_second": lead_over_second if primary_domain else None,
            "streak_matches": streak,
            "band_width": band,
            "eligible": achilles_eligible,
        },
        "focus": focus,
    }}


# Weights endpoints (admin-gated)
def _is_admin() -> bool:
    import os
    return os.getenv("LOLTRACK_ADMIN") == "1"


@router.get("/gis/weights")
def get_weights():
    roles = load_role_weights()
    # Map to API-facing role keys and Title Case domains
    api_roles = {}
    role_alias_out = {"MIDDLE": "MID", "BOTTOM": "ADC", "UTILITY": "SUPPORT"}
    for r_int, dmap in roles.items():
        r_api = role_alias_out.get(r_int.upper(), r_int.upper())
        api_roles[r_api] = {k.capitalize(): float(v) for k, v in dmap.items()}
    return {"ok": True, "data": {"schema_version": "weights.v1", "roles": api_roles}}


@router.put("/gis/weights")
def put_weights(payload: Dict[str, Any]):
    roles = (payload or {}).get("roles")
    if not isinstance(roles, dict) or not roles:
        return {"ok": False, "error": {"code": "INVALID", "message": "roles map required"}}
    # Normalize and validate
    from core.gis import _normalize_role_map as _norm, DOMAINS as _DOMS, _weights_path as _wpath
    norm = _norm(roles)
    # Validate required roles present
    required_roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    for rr in required_roles:
        if rr not in norm:
            return {"ok": False, "error": {"code": "INVALID", "message": f"missing role {rr}"}}
    # Validate sums and domain keys
    for r, dmap in norm.items():
        total = sum(dmap.get(d, 0.0) for d in _DOMS)
        if abs(total - 1.0) > 1e-6:
            return {"ok": False, "error": {"code": "INVALID", "message": f"weights for {r} must sum to 1.0"}}
        unknown = [k for k in dmap.keys() if k not in _DOMS]
        if unknown:
            return {"ok": False, "error": {"code": "INVALID", "message": f"unknown domains {unknown}"}}
    # Persist to weights.json
    import json, logging, os
    path = _wpath()
    try:
        # diff old→new for log
        old = load_role_weights()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"roles": roles}, f, indent=2)
        logging.getLogger(__name__).info("weights updated at %s", path)
        # Return effective roles
        return get_weights()
    except Exception as e:
        return {"ok": False, "error": {"code": "WRITE_FAILED", "message": str(e)}}


@router.post("/gis/backfill")
def backfill_inst(limit: int = 200, queue: Optional[int] = Query(None)):
    """Backfill per-match domain contributions for recent matches in chronological order.

    Runs the same pipeline used after ingest (with smoothing/clamps), but also persists per-match inst_contrib
    so drawers open fast. Useful when contributions are missing for older matches.
    """
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot ID in Settings."}}
    from core.gis import process_new_matches as _process
    store = Store()
    # process all matches for the player (optionally queue-filtered). list_matches_for_player returns ASC (oldest first)
    count = 0
    try:
        rows = store.list_matches_for_player(puuid, queue)
        rows = rows[-int(limit):] if limit and limit > 0 else rows
        for r in rows:
            mid = r["match_id"]
            # Skip if we already have inst rows
            if store.seen_inst_for_match(mid, puuid):
                continue
            # Use the same function that persists inst_contrib and smoothed scores
            try:
                from core.gis import update_scores_for_match as _update
                res = _update(store, puuid, mid)
                if res is not None:
                    count += 1
            except Exception:
                # Non-blocking: continue on errors
                pass
        return {"ok": True, "data": {"backfilled": count}}
    except Exception as e:
        return {"ok": False, "error": {"code": "BACKFILL_ERR", "message": str(e)}}


@router.post("/gis/rebuild-all")
def rebuild_all(clear: bool = Query(True), queue: Optional[int] = Query(None)):
    """Recalculate contributions and smoothed scores for all matches, then rebuild rolling windows.

    - If clear=True, clears previous inst_contrib, score_domain, score_overall, norm_state for this player first.
    - Processes matches chronologically to warm baselines.
    - Rebuilds windows for current queue setting.
    """
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot ID in Settings."}}
    store = Store()
    cleared = {"inst": 0, "domain": 0, "overall": 0, "norm": 0, "windows": 0}
    if clear:
        try:
            with store.connect() as con:
                c1 = con.execute("DELETE FROM inst_contrib WHERE puuid=?", (puuid,)).rowcount or 0
                c2 = con.execute("DELETE FROM score_domain WHERE player_id=?", (puuid,)).rowcount or 0
                c3 = con.execute("DELETE FROM score_overall WHERE player_id=?", (puuid,)).rowcount or 0
                c4 = con.execute("DELETE FROM norm_state WHERE player_id=?", (puuid,)).rowcount or 0
                c5 = con.execute("DELETE FROM windows WHERE key LIKE ?", (f"puuid:{puuid}:%",)).rowcount or 0
                con.commit()
                cleared = {"inst": c1, "domain": c2, "overall": c3, "norm": c4, "windows": c5}
        except Exception:
            pass
    # Process matches
    backfilled = 0
    smoothed = 0
    rows = store.list_matches_for_player(puuid, queue)
    for r in rows:
        mid = r["match_id"]
        try:
            # First, ensure per-match inst contributions (no gating/clamps)
            try:
                payload = _gis.ensure_inst_contrib(mid, puuid, force=True)
                if payload and bool(payload.get("computed", False)):
                    backfilled += 1
            except Exception:
                pass
            # Then, update smoothed scores (ranked gating included)
            res = _gis.update_scores_for_match(store, puuid, mid)
            if res is not None:
                smoothed += 1
        except Exception:
            # continue through failures
            pass
    # Second pass: recompute again now that baselines warmed (stabilize earliest matches)
    try:
        for r in rows:
            mid = r["match_id"]
            try:
                _gis.ensure_inst_contrib(mid, puuid, force=True)
            except Exception:
                pass
    except Exception:
        pass
    # Rebuild windows
    try:
        _rebuild_windows(store, cfg)
    except Exception:
        pass
    return {"ok": True, "data": {"backfilled": backfilled, "smoothed": smoothed, "cleared": cleared}}

def suggestion_for(domain: str, metric: str):
    m = metric
    d = domain
    # Basic mapping; expand as needed
    if d == 'laning':
        if m == 'csd10': return 'CS lead at 10 is below baseline; aim for +12 CS by 15m.'
        if m == 'gd10': return 'Gold diff at 10 is lagging; manage waves to take plates.'
        if m == 'xpd10': return 'XP diff at 10 is low; consider safer trades and wave control.'
        if m == 'early_deaths_pre10': return 'Early deaths pre-10 are frequent; track jungler and ward river earlier.'
    if d == 'vision':
        if m == 'vision_per_min': return 'Vision/min below baseline; place wards on spawn and refresh control wards.'
        if m == 'wards_killed': return 'Few ward clears; buy sweepers and look for common ward spots.'
        if m == 'ctrl_wards_pre14': return 'Low control wards pre-14; buy and place one before 10m.'
    if d == 'objectives':
        if m == 'obj_participation': return 'Low objective presence; plan earlier rotations to dragons/herald.'
        if m == 'obj_near': return 'Far from objectives; hover and set vision 60–90s before spawn.'
        if m == 'kp_early': return 'Low early KP; coordinate early skirmishes around objectives.'
    if d == 'economy':
        if m == 'csmin14': return 'CS/min by 14 is low; focus on last-hitting and safe farm.'
        if m == 'gpm': return 'GPM low; secure waves between objectives and avoid unnecessary roams.'
        if m == 'mythic_at_s': return 'Late mythic timing; plan recalls to hit earlier spike.'
    if d == 'damage':
        if m == 'dpm': return 'DPM behind baseline; look for safe DPS windows in fights.'
        if m == 'damage_share': return 'Low damage share; pick fights where you can contribute safely.'
    if d == 'discipline':
        if m == 'time_dead_per_min': return 'High time dead; choose safer angles and track enemy threats.'
        if m == 'early_deaths_pre10': return 'Early deaths; respect wave states and jungler timings.'
    if d == 'macro':
        if m == 'roam_distance_pre14': return 'Roams aren’t paying off; balance roams with farm/plates.'
        if m == 'obj_near': return 'Slow to objectives; rotate earlier and ping team to group.'
    return None


@router.get("/gis/match/{match_id}")
def gis_match(match_id: str, recompute: Optional[bool] = Query(False), debug: Optional[bool] = Query(False)):
    """Compute-on-open for per-match domain contributions.

    Behavior: return existing inst_contrib if present; otherwise compute now from
    stored match + timeline (or fetch), persist, and return in one response.
    No ranked-only filtering here.
    """
    t0 = time.time()
    logger = logging.getLogger(__name__)
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add your Riot ID in Settings."}}
    store = Store()
    # Try cache first (unless recompute requested)
    if not recompute:
        cached = store.get_inst_contrib(match_id, puuid)
        if cached:
            ms = (time.time() - t0) * 1000.0
            # Sanity log: include roleResolved, domainsInstJSON, zMetricsCount
            try:
                store = Store()
                with store.connect() as con:
                    row = con.execute("SELECT role FROM matches WHERE match_id=?", (match_id,)).fetchone()
                role_resolved = (row[0] if row and row[0] else None)
            except Exception:
                role_resolved = None
            z_count = 0
            try:
                z_count = sum(len(v or {}) for v in (cached.get("z") or {}).values())
            except Exception:
                z_count = 0
            logger.info(
                "/gis/match computed_on_open",
                extra={
                    "matchId": match_id,
                    "puuid": puuid,
                    "roleResolved": role_resolved,
                    "domainsInstJSON": json.dumps(cached.get("domains") or {}),
                    "zMetricsCount": int(z_count),
                    "computed": False,
                    "ms": round(ms, 1),
                },
            )
            # Ensure computed flag in payload for acceptance checks
            cached["computed"] = False
            return {"ok": True, "data": cached}
    # Compute if missing
    try:
        payload = _gis.ensure_inst_contrib(match_id, puuid, force=bool(recompute))
        ms = (time.time() - t0) * 1000.0
        # Sanity log: include resolved role, domains and z-count
        try:
            store = Store()
            with store.connect() as con:
                row = con.execute("SELECT role FROM matches WHERE match_id=?", (match_id,)).fetchone()
            role_resolved = (row[0] if row and row[0] else None)
        except Exception:
            role_resolved = None
        z_count = 0
        try:
            z_count = sum(len(v or {}) for v in (payload.get("z") or {}).values())
        except Exception:
            z_count = 0
        # Extra debug: attach domains debug summary to response and log clearly to console
        try:
            zmap = payload.get("z") or {}
            dbg = {d: {"inputs": len((zmap.get(d) or {})), "metrics": list((zmap.get(d) or {}).keys()), "value": float(payload.get("domains", {}).get(d, 0.0))} for d in (payload.get("domains") or {}).keys()}
            payload["debug"] = dbg
            # Always emit a concise, copy/paste-friendly line via uvicorn.access
            try:
                # Log via uvicorn.error to avoid AccessFormatter tuple expectations
                elog = logging.getLogger("uvicorn.error")
                parts = []
                for d in sorted(dbg.keys()):
                    ent = dbg[d]
                    parts.append(f"{d}: inputs={ent['inputs']} value={ent['value']:.2f} metrics={','.join(ent['metrics']) if ent['metrics'] else '-'}")
                elog.info("/gis/match debug matchId=%s %s", match_id, " | ".join(parts))
            except Exception:
                pass
            if debug:
                logger.info("/gis/match debug", extra={"matchId": match_id, "domains": dbg})
        except Exception:
            pass
        logger.info(
            "/gis/match computed_on_open",
            extra={
                "matchId": match_id,
                "puuid": puuid,
                "roleResolved": role_resolved,
                "domainsInstJSON": json.dumps(payload.get("domains") or {}),
                "zMetricsCount": int(z_count),
                "computed": True,
                "ms": round(ms, 1),
            },
        )
        return {"ok": True, "data": payload}
    except Exception as e:
        # Map common errors: not found vs other
        from fastapi import HTTPException
        msg = str(e)
        if "not found" in msg.lower() or "404" in msg or "invalid" in msg.lower():
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "matchId not found; pass metadata.matchId (like NA1_123...)."})
        # Unknown failure
        logger.exception("/gis/match error for %s", match_id)
        raise HTTPException(status_code=500, detail={"code": "compute_failed", "message": "Failed to compute contributions."})
