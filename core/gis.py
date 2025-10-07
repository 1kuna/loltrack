from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .store import Store
from .metrics import MS, find_frame_at, lane_opponent_id, participant_by_puuid
from .metrics_extras import compute_extras
from .config import get_config
from .riot import RiotClient


DOMAINS = [
    "laning",
    "economy",
    "damage",
    "objectives",
    "vision",
    "discipline",
    "macro",
]


def _alpha_from_hl(half_life_games: float) -> float:
    return 1.0 - (0.5 ** (1.0 / max(half_life_games, 1e-6)))


HL_METRIC = 6.0
HL_DOMAIN = 8.0
HL_OVERALL = 10.0


def _reliability(duration_s: int, queue_id: Optional[int]) -> float:
    # Base on minutes played; early surrenders weaken update
    r = min(1.0, max(0.0, (duration_s or 0) / 1800.0))
    # Reduce for non-ranked SR queues if provided
    if queue_id is not None and queue_id not in (420, 440):  # Solo/Duo, Flex
        r *= 0.6
    # Ignore ARAM/custom entirely for GIS
    if queue_id in (450, 460, 490):
        r = 0.0
    return float(r)


def _team_damage_share(match: Dict[str, Any], puuid: str) -> float:
    info = match.get("info", {})
    parts = info.get("participants", [])
    me = next((p for p in parts if p.get("puuid") == puuid), None) or {}
    team_id = int(me.get("teamId") or 0)
    my = float(me.get("totalDamageDealtToChampions") or 0.0)
    team = 0.0
    for p in parts:
        if int(p.get("teamId") or 0) == team_id:
            team += float(p.get("totalDamageDealtToChampions") or 0.0)
    if team <= 0:
        return 0.0
    return max(0.0, min(100.0, (my / team) * 100.0))


def _early_deaths_pre(match: Dict[str, Any], timeline: Dict[str, Any], pid: int, minute: int = 10) -> int:
    count = 0
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            if ev.get("type") == "CHAMPION_KILL" and int(ev.get("victimId") or 0) == pid and int(ev.get("timestamp") or 0) < minute * 60 * MS:
                count += 1
    return count


def _cs_from_pf(pf: Dict[str, Any]) -> int:
    return int((pf.get("minionsKilled") or 0) + (pf.get("jungleMinionsKilled") or 0))


def _csd_at(match: Dict[str, Any], timeline: Dict[str, Any], pid: int, minute: int) -> Optional[int]:
    opp = lane_opponent_id(match, timeline, pid)
    fr = find_frame_at(timeline, minute * 60 * MS)
    pfs = fr.get("participantFrames", {}) if fr else {}
    me = pfs.get(str(pid), {})
    if opp:
        op = pfs.get(str(opp), {})
        return int(_cs_from_pf(me) - _cs_from_pf(op))
    # Without opponent, fallback to cs itself as neutral (diff ~ 0) by returning None
    return None


def _time_dead_per_min(match: Dict[str, Any], puuid: str) -> float:
    info = match.get("info", {})
    parts = info.get("participants", [])
    me = next((p for p in parts if p.get("puuid") == puuid), None) or {}
    dead_s = float(me.get("totalTimeSpentDead") or 0.0)
    dur_min = max(1.0, float(info.get("gameDuration") or 1) / 60.0)
    return dead_s / dur_min


def _obj_near_count(match: Dict[str, Any], timeline: Dict[str, Any], pid: int) -> int:
    # Count objective events where we are within ~2500 units
    info = match.get("info", {})
    parts = info.get("participants", [])
    me = next((p for p in parts if p.get("participantId") == pid), None) or {}
    my_team = int(me.get("teamId") or 0)
    def pos_near(ts: int) -> Optional[Tuple[float, float]]:
        frames = timeline.get("info", {}).get("frames", []) or []
        if not frames:
            return None
        fr = min(frames, key=lambda f: abs(int(f.get("timestamp") or 0) - ts))
        pf = fr.get("participantFrames", {}).get(str(pid), {})
        pos = pf.get("position") or {}
        x = pos.get("x"); y = pos.get("y")
        if x is None or y is None:
            return None
        return float(x), float(y)
    near = 0
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            typ = ev.get("type")
            if typ in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
                killer = int(ev.get("killerId") or 0)
                kteam = None
                for p in parts:
                    if int(p.get("participantId") or 0) == killer:
                        kteam = int(p.get("teamId") or 0)
                        break
                if kteam != my_team:
                    continue
                ts = int(ev.get("timestamp") or 0)
                mp = pos_near(ts)
                ep = ev.get("position") or {}
                ex = ep.get("x"); ey = ep.get("y")
                if mp and ex is not None and ey is not None:
                    dx = mp[0] - float(ex)
                    dy = mp[1] - float(ey)
                    if (dx * dx + dy * dy) ** 0.5 <= 2500:
                        near += 1
    return near


def _is_low_mastery(puuid: str, champion_id: int) -> bool:
    """Best-effort check for low mastery on a champion.

    Uses cached meta if available; otherwise fetches champion masteries and caches a low-masteries set.
    Low mastery if champion mastery points in bottom 20% or level <= 4.
    """
    from .store import Store as _Store
    st = _Store()
    key_low = f"mastery_low:{puuid}"
    raw = st.get_meta(key_low)
    import json as _json
    if raw:
        try:
            low_set = set(_json.loads(raw) or [])
            return int(champion_id) in low_set
        except Exception:
            pass
    # Build cache
    try:
        cfg = get_config()
        rc = RiotClient.from_config(cfg, kind="bg")
        lst = rc.champion_masteries_by_puuid(puuid)
        points = [int(x.get("championPoints") or 0) for x in lst]
        if not points:
            return False
        pts_sorted = sorted(points)
        import math as _math
        idx20 = max(0, min(len(pts_sorted)-1, int(0.2 * (len(pts_sorted)-1))))
        thr = pts_sorted[idx20]
        low_ids = []
        for x in lst:
            pid = int(x.get("championId") or 0)
            lvl = int(x.get("championLevel") or 0)
            pts = int(x.get("championPoints") or 0)
            if lvl <= 4 or pts <= thr:
                low_ids.append(pid)
        st.set_meta(key_low, _json.dumps(low_ids))
        return int(champion_id) in set(low_ids)
    except Exception:
        # On any failure, avoid applying the guardrail (false)
        return False


def _load_match_and_timeline(store: Store, match_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with store.connect() as con:
        row_m = con.execute("SELECT raw_json FROM matches WHERE match_id=?", (match_id,)).fetchone()
        row_t = con.execute("SELECT raw_json FROM timelines WHERE match_id=?", (match_id,)).fetchone()
    match = json.loads(row_m[0]) if row_m and row_m[0] else {}
    timeline = json.loads(row_t[0]) if row_t and row_t[0] else {"info": {"frames": []}}
    return match, timeline


def _extract_features(store: Store, match_id: str, puuid: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    match, timeline = _load_match_and_timeline(store, match_id)
    info = match.get("info", {})
    parts = info.get("participants", [])
    mep = participant_by_puuid(match, puuid)
    pid = int(mep.get("participantId") or 0)
    duration_s = int(info.get("gameDuration") or 0)

    # Compute extras (from cache or on-the-fly); store cache if missing
    # Attempt to fetch cached row for speed
    with store.connect() as con:
        ex = con.execute("SELECT * FROM metrics_extras WHERE match_id=?", (match_id,)).fetchone()
        mx = con.execute("SELECT * FROM metrics WHERE match_id=?", (match_id,)).fetchone()
    if ex is None:
        computed = compute_extras(match, timeline, None, puuid)
        store.upsert_metrics_extras(match_id, {"match_id": match_id, **computed["extras_row"]})
        # Re-fetch row to use consistent access pattern
        with store.connect() as con:
            ex = con.execute("SELECT * FROM metrics_extras WHERE match_id=?", (match_id,)).fetchone()
    # Guard for missing metrics
    # Build values
    vals: Dict[str, float] = {}
    # Laning diffs
    try:
        f10 = find_frame_at(timeline, 10 * 60 * MS)
        f15 = find_frame_at(timeline, 15 * 60 * MS)
        pf10 = f10.get("participantFrames", {}).get(str(pid), {})
        pf15 = f15.get("participantFrames", {}).get(str(pid), {})
        opp = lane_opponent_id(match, timeline, pid)
        op10 = f10.get("participantFrames", {}).get(str(opp), {}) if opp else {}
        op15 = f15.get("participantFrames", {}).get(str(opp), {}) if opp else {}
        vals["gd10"] = float((pf10.get("totalGold") or 0) - (op10.get("totalGold") or 0))
        vals["xpd10"] = float((pf10.get("xp") or 0) - (op10.get("xp") or 0))
        vals["gd15"] = float((pf15.get("totalGold") or 0) - (op15.get("totalGold") or 0))
        vals["xpd15"] = float((pf15.get("xp") or 0) - (op15.get("xp") or 0))
        csd10 = _csd_at(match, timeline, pid, 10)
        csd14 = _csd_at(match, timeline, pid, 14)
        if csd10 is not None:
            vals["csd10"] = float(csd10)
        if csd14 is not None:
            vals["csd14"] = float(csd14)
    except Exception:
        pass
    # Early deaths and plates
    try:
        vals["early_deaths_pre10"] = float(_early_deaths_pre(match, timeline, pid, 10))
        # Plates pre-14 credited if killerId is me (simple heuristic)
        plates = 0
        for fr in timeline.get("info", {}).get("frames", []) or []:
            for ev in fr.get("events", []) or []:
                if ev.get("type") == "TURRET_PLATE_DESTROYED" and int(ev.get("timestamp") or 0) < 14 * 60 * MS:
                    if int(ev.get("killerId") or 0) == pid:
                        plates += 1
        vals["plates_pre14"] = float(plates)
    except Exception:
        pass
    # From extras row
    try:
        vals["dpm"] = float(ex["dpm"]) if ex and ex["dpm"] is not None else 0.0
        vals["gpm"] = float(ex["gpm"]) if ex and ex["gpm"] is not None else 0.0
        vals["obj_participation"] = float(ex["obj_participation"]) if ex and ex["obj_participation"] is not None else 0.0
        vals["dmg_obj"] = float(ex["dmg_obj"]) if ex and ex["dmg_obj"] is not None else 0.0
        vals["dmg_turrets"] = float(ex["dmg_turrets"]) if ex and ex["dmg_turrets"] is not None else 0.0
        mythic_at_s = int(ex["mythic_at_s"]) if ex and ex["mythic_at_s"] is not None else 0
        two_item_at_s = int(ex["two_item_at_s"]) if ex and ex["two_item_at_s"] is not None else 0
        if mythic_at_s:
            vals["mythic_at_s"] = float(mythic_at_s)
        if two_item_at_s:
            vals["two_item_at_s"] = float(two_item_at_s)
        vals["vision_per_min"] = float(ex["vision_per_min"]) if ex and ex["vision_per_min"] is not None else 0.0
        vals["wards_killed"] = float(ex["wards_killed"]) if ex and ex["wards_killed"] is not None else 0.0
        vals["roam_distance_pre14"] = float(ex["roam_distance_pre14"]) if ex and ex["roam_distance_pre14"] is not None else 0.0
    except Exception:
        pass
    # From metrics row
    try:
        if mx is not None:
            vals["ctrl_wards_pre14"] = float(mx["ctrl_wards_pre14"]) if mx["ctrl_wards_pre14"] is not None else 0.0
            vals["csmin14"] = float(mx["csmin14"]) if mx["csmin14"] is not None else 0.0
            vals["kp_early"] = float(mx["kp_early"]) if mx["kp_early"] is not None else 0.0
    except Exception:
        pass
    # Derived metrics
    try:
        vals["damage_share"] = _team_damage_share(match, puuid)
        vals["time_dead_per_min"] = _time_dead_per_min(match, puuid)
        vals["obj_near"] = float(_obj_near_count(match, timeline, pid))
    except Exception:
        pass

    meta = {
        "queue_id": int(info.get("queueId") or 0),
        "role": mep.get("teamPosition") or None,
        "duration_s": duration_s,
    }
    return vals, meta


# Domain sub-metric weights (role-aware)
ROLE_DOMAIN_WEIGHTS: Dict[str, Dict[str, float]] = {
    "TOP": {"laning": .30, "economy": .20, "damage": .15, "macro": .15, "objectives": .10, "vision": .05, "discipline": .05},
    "JUNGLE": {"objectives": .30, "macro": .20, "laning": .10, "economy": .10, "damage": .10, "vision": .10, "discipline": .10},
    "MIDDLE": {"laning": .28, "damage": .20, "economy": .18, "macro": .14, "objectives": .10, "vision": .05, "discipline": .05},
    "BOTTOM": {"economy": .25, "damage": .22, "laning": .22, "objectives": .12, "macro": .09, "vision": .05, "discipline": .05},
    "UTILITY": {"vision": .28, "objectives": .20, "macro": .14, "laning": .14, "damage": .12, "economy": .06, "discipline": .06},
}

# Per-domain metric weights (weights sum does not need to be 1; normalized)
DOMAIN_METRIC_WEIGHTS: Dict[str, Dict[str, float]] = {
    "laning": {
        "gd10": 0.35,
        "xpd10": 0.25,
        "csd10": 0.25,
        "early_deaths_pre10": -0.15,
        "plates_pre14": 0.10,  # computed via extras overview; fallback from events
    },
    "economy": {
        "csmin14": 0.40,
        "gpm": 0.35,
        "mythic_at_s": -0.15,
        "two_item_at_s": -0.10,
    },
    "damage": {
        "dpm": 0.6,
        "damage_share": 0.4,
    },
    "objectives": {
        "obj_participation": 0.60,
        "obj_near": 0.25,
        "kp_early": 0.15,
    },
    "vision": {
        "vision_per_min": 0.50,
        "wards_killed": 0.25,
        "ctrl_wards_pre14": 0.25,
    },
    "discipline": {
        "time_dead_per_min": -0.70,
        "early_deaths_pre10": -0.30,
    },
    "macro": {
        "roam_distance_pre14": 0.60,
        "obj_near": 0.40,
    },
}

# Role domain weights: default presets
_DEFAULT_ROLE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "TOP": {"laning": .30, "economy": .20, "damage": .15, "macro": .15, "objectives": .10, "vision": .05, "discipline": .05},
    "JUNGLE": {"objectives": .30, "macro": .20, "laning": .10, "economy": .10, "damage": .10, "vision": .10, "discipline": .10},
    "MIDDLE": {"laning": .28, "damage": .20, "economy": .18, "macro": .14, "objectives": .10, "vision": .05, "discipline": .05},
    "BOTTOM": {"economy": .25, "damage": .22, "laning": .22, "objectives": .12, "macro": .09, "vision": .05, "discipline": .05},
    "UTILITY": {"vision": .28, "objectives": .20, "macro": .14, "laning": .14, "damage": .12, "economy": .06, "discipline": .06},
}

import os, json as _json
from pathlib import Path as _Path
from .config import _user_config_dir as _cfgdir  # type: ignore


def _weights_path() -> str:
    p = os.getenv("LOLTRACK_WEIGHTS_PATH")
    if p:
        return p
    return str(_cfgdir() / "weights.json")


def _normalize_role_map(raw_roles: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    # Accept API-facing aliases and Title Case domains; normalize to internal keys
    role_alias = {"MID": "MIDDLE", "ADC": "BOTTOM", "SUPPORT": "UTILITY"}
    out: Dict[str, Dict[str, float]] = {}
    for r, dmap in raw_roles.items():
        r_int = role_alias.get(r.upper(), r.upper())
        doms = {}
        for k, v in dmap.items():
            doms[k.lower()] = float(v)
        out[r_int] = doms
    return out


def load_role_weights() -> Dict[str, Dict[str, float]]:
    """Load role domain weights from weights.json; fallback to defaults."""
    path = _weights_path()
    try:
        p = _Path(path)
        if not p.exists():
            return _DEFAULT_ROLE_WEIGHTS
        data = _json.loads(p.read_text())
        roles = data.get("roles") if isinstance(data, dict) else data
        if not isinstance(roles, dict):
            return _DEFAULT_ROLE_WEIGHTS
        out = _normalize_role_map(roles)
        # Validate domains
        for r, m in out.items():
            tot = sum(m.get(d, 0.0) for d in DOMAINS)
            if tot <= 0:
                return _DEFAULT_ROLE_WEIGHTS
        return out
    except Exception:
        return _DEFAULT_ROLE_WEIGHTS


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _huber_clip_z(z: float, k: float = 2.5) -> float:
    return _clip(z, -k, k)


def _standardize(store: Store, puuid: str, queue: Optional[int], role: Optional[str], metrics: Dict[str, float], huber_k: float = 2.5) -> Tuple[Dict[str, float], Dict[str, Tuple[float, float]]]:
    out: Dict[str, float] = {}
    states: Dict[str, Tuple[float, float]] = {}
    alpha = _alpha_from_hl(HL_METRIC)
    eps_map = {
        "gd10": 50.0, "gd15": 60.0, "xpd10": 50.0, "xpd15": 60.0,
        "csd10": 1.0, "csd14": 1.0, "csmin14": 0.2,
        "dpm": 50.0, "gpm": 20.0, "damage_share": 2.0,
        "obj_participation": 5.0, "obj_near": 0.5,
        "vision_per_min": 0.1, "wards_killed": 0.2, "ctrl_wards_pre14": 0.2,
        "early_deaths_pre10": 0.2, "time_dead_per_min": 1.0,
        "mythic_at_s": 30.0, "two_item_at_s": 30.0, "kp_early": 5.0,
        "dmg_obj": 50.0, "dmg_turrets": 50.0,
    }
    for m, x in metrics.items():
        mu, var = store.load_norm(puuid, queue, role, m)
        if mu is None or var is None:
            # Seed with current value and a small variance to avoid div-by-zero; we will warm over first few matches
            mu = float(x)
            var = float(eps_map.get(m, 1.0)) ** 2
        # Update EWMA mean/var with current x
        # EWMA mean
        mu_new = mu + alpha * (float(x) - mu)
        # EWMA variance (exponentially weighted). Using classical form: var_t = (1-alpha)*(var_{t-1} + alpha*(x - mu_{t-1})^2)
        var_new = (1.0 - alpha) * (var + alpha * (float(x) - mu) ** 2)
        # Save state back
        store.upsert_norm(puuid, queue, role, m, mu_new, var_new)
        states[m] = (mu_new, var_new)
        std = (var_new ** 0.5) if var_new > 1e-6 else float(eps_map.get(m, 1.0))
        z = (float(x) - mu_new) / max(std, 1e-6)
        out[m] = _huber_clip_z(z, huber_k)
    return out, states


def _domain_inst_scores(role: Optional[str], z: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """Compute per-domain instantaneous 0-100 scores and include per-metric contributions for debugging."""
    role_key = (role or "").upper()
    Wd = DOMAIN_METRIC_WEIGHTS
    inst: Dict[str, float] = {}
    contribs: Dict[str, Dict[str, float]] = {}
    for d, weights in Wd.items():
        s = 0.0
        tw = 0.0
        per_m: Dict[str, float] = {}
        for m, w in weights.items():
            if m not in z:
                continue
            tw += abs(w)
            per = w * _clip(z[m], -3.0, 3.0)
            per_m[m] = per
            s += per
        if tw <= 0:
            inst[d] = 50.0
        else:
            # Normalize by total weight magnitude so scales are comparable
            s_norm = s / tw
            inst[d] = 50.0 + 10.0 * s_norm
        contribs[d] = per_m
    return inst, contribs


def _overall_inst(role: Optional[str], domain_inst: Dict[str, float]) -> float:
    role_key = (role or "").upper()
    # Load effective weights (file-backed)
    W = load_role_weights().get(role_key) or load_role_weights().get("UTILITY") or _DEFAULT_ROLE_WEIGHTS.get("UTILITY")
    # Ensure weights sum to 1
    total = sum(W.values()) or 1.0
    out = 50.0
    for d, wk in W.items():
        if d in domain_inst:
            out += (wk / total) * (domain_inst[d] - 50.0)
    return out


def update_scores_for_match(store: Store, puuid: str, match_id: str) -> Optional[Dict[str, Any]]:
    """Compute and persist GIS components for a single match.

    Returns a summary dict for diagnostics, or None if match should be skipped.
    """
    # Load basic context
    with store.connect() as con:
        m = con.execute("SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
        if not m:
            return None
    queue_id = int(m["queue_id"] or 0)
    current_patch = str(m["patch"] or "")
    # Queue gating: only ranked SR by config (and skip ARAM/custom defensively)
    try:
        cfg_local = get_config()
        ranked_qs = set(int(x) for x in (cfg_local.get("gis", {}).get("rankedQueues") or [420, 440]))
    except Exception:
        ranked_qs = {420, 440}
    if (queue_id not in ranked_qs) or (queue_id in (450, 460, 490)):
        return None
    vals, meta = _extract_features(store, match_id, puuid)
    role = meta.get("role")
    duration_s = int(meta.get("duration_s") or 0)
    r = _reliability(duration_s, queue_id)
    if r <= 0.0:
        return None

    # Patch-change easing for Huber threshold (wider for first few games of a new patch)
    huber_k = 2.5
    try:
        key = f"patch_ease:{puuid}:{queue_id}:{role or ''}"
        raw = store.get_meta(key)
        import json as _json
        state = _json.loads(raw) if raw else None
        if (state or {}).get("patch") != current_patch:
            state = {"patch": current_patch, "remain": 3}
        if (state or {}).get("remain", 0) > 0:
            huber_k = 3.0
            state["remain"] = int(state.get("remain", 0)) - 1
        store.set_meta(key, _json.dumps(state))
    except Exception:
        pass

    # Standardize vs personal baselines for this (queue, role)
    # Use queue exactly; do not bleed across queues
    z, states = _standardize(store, puuid, queue_id, role, vals, huber_k=huber_k)

    # Domain inst 0..100
    inst_domains, per_metric_contrib = _domain_inst_scores(role, z)

    # Champion mastery guardrail: cap negative per-domain impact if champion is low mastery
    try:
        champ_id = int(m["champion_id"] or 0)
        if champ_id and _is_low_mastery(puuid, champ_id):
            try:
                cap = float((get_config().get("gis", {}) or {}).get("maxNegativeImpactLowMastery", 3.0))
            except Exception:
                cap = 3.0
            for d in list(inst_domains.keys()):
                if (inst_domains[d] - 50.0) < -cap:
                    inst_domains[d] = 50.0 - cap
    except Exception:
        pass

    # Smooth domain scores
    alpha_d = _alpha_from_hl(HL_DOMAIN)
    for d, inst_val in inst_domains.items():
        prev = store.load_domain_score(puuid, queue_id, role, d) or 50.0
        new = prev + r * alpha_d * (inst_val - prev)
        store.upsert_domain_score(puuid, queue_id, role, d, new)
        # Write inst contribution for drill-down, including z map of the metrics used in this domain
        z_for_domain = {m: z[m] for m in DOMAIN_METRIC_WEIGHTS.get(d, {}).keys() if m in z}
        store.upsert_inst_contrib(match_id, puuid, d, inst_val, json.dumps(z_for_domain))

    # Overall inst and smoothing with clamp on delta
    inst_overall = _overall_inst(role, inst_domains)
    prev_overall = store.load_overall_score(puuid, queue_id, role) or 50.0
    alpha_o = _alpha_from_hl(HL_OVERALL)
    # Clamp per-match overall delta before smoothing to +/- 6 points
    delta = inst_overall - prev_overall
    delta = _clip(delta, -6.0, 6.0)
    new_overall = prev_overall + r * alpha_o * delta
    store.upsert_overall_score(puuid, queue_id, role, new_overall)

    return {
        "queue": queue_id,
        "role": role,
        "r": r,
        "inst_domains": inst_domains,
        "inst_overall": inst_overall,
        "overall": new_overall,
    }


def process_new_matches(store: Store, puuid: str, queue_filter: Optional[int] = None) -> int:
    """Process all matches for player (chronologically) and compute GIS for those lacking inst rows."""
    rows = store.list_matches_for_player(puuid, queue_filter)
    done = 0
    for r in rows:
        mid = r["match_id"]
        if store.seen_inst_for_match(mid, puuid):
            continue
        res = update_scores_for_match(store, puuid, mid)
        if res is not None:
            done += 1
    return done


def achilles_and_secondary(store: Store, puuid: str, queue: Optional[int], role: Optional[str], last_n: int = 8, ranked_queues: Optional[List[int]] = None) -> Dict[str, Any]:
    """Compute Achilles heel and secondary domains based on recent inst deficits with hysteresis-like rule.

    Uses last N matches' inst_contrib for this (player, queue, role).
    """
    with store.connect() as con:
        base = (
            "SELECT i.match_id, i.domain, i.inst_score "
            "FROM inst_contrib i JOIN matches m ON m.match_id = i.match_id "
            "WHERE i.puuid=? "
        )
        params: list[Any] = [puuid]
        rq = list(int(x) for x in (ranked_queues or [420, 440]))
        if rq:
            base += f"AND m.queue_id IN ({','.join(['?']*len(rq))}) "
            params.extend(rq)
        if queue is not None:
            base += "AND m.queue_id=? "
            params.append(queue)
        if role:
            base += "AND m.role=? "
            params.append(role)
        base += "ORDER BY m.game_creation_ms DESC LIMIT ?"
        params.append(max(20, last_n))
        rows = con.execute(base, params).fetchall()
    # Build per-match domain deficits (inst - 50)
    seq: List[Dict[str, float]] = []
    by_match: Dict[str, Dict[str, float]] = {}
    for r in rows:
        mid = r["match_id"]
        by_match.setdefault(mid, {})[r["domain"]] = float(r["inst_score"]) - 50.0
    # Latest first; convert to list
    for mid, dmap in by_match.items():
        seq.append(dmap)
    if not seq:
        return {"primary": None, "secondary": [], "deficits": {}}
    # Compute EWMA of deficits per domain
    alpha = _alpha_from_hl(4.0)
    agg: Dict[str, float] = {d: 0.0 for d in DOMAINS}
    seen: Dict[str, bool] = {d: False for d in DOMAINS}
    for mdef in reversed(seq[:last_n]):  # oldest -> newest
        for d in DOMAINS:
            if d in mdef:
                if not seen[d]:
                    agg[d] = mdef[d]
                    seen[d] = True
                else:
                    agg[d] = alpha * mdef[d] + (1 - alpha) * agg[d]
    # Determine ordering
    ordered = sorted([(d, agg.get(d, 0.0)) for d in DOMAINS], key=lambda x: x[1])
    primary = None
    if ordered:
        cand, val = ordered[0]
        # Hysteresis-lite: ensure candidate was min by at least 2 points in last 3 matches
        stable = 0
        for mdef in seq[:3]:  # latest 3
            vals = [(d, mdef.get(d, 0.0)) for d in DOMAINS]
            vals.sort(key=lambda x: x[1])
            if vals and vals[0][0] == cand and (len(vals) == 1 or (vals[1][1] - vals[0][1]) >= 2.0):
                stable += 1
        if val <= -4.0 and stable >= 3:
            primary = cand
    secondary = [d for d, v in ordered[1:3] if v <= -2.0]
    return {"primary": primary, "secondary": secondary, "deficits": {d: round(v, 2) for d, v in ordered}}
