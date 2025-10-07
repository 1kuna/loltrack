from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dateutil import parser as dateparser

from .store import Store
from .riot import RiotClient


MS = 1000


def _ts_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _parse_since(since: Optional[str]) -> Optional[int]:
    if not since:
        return None
    s = since.strip().lower()
    now = datetime.now(timezone.utc)
    if s.endswith("d") and s[:-1].isdigit():
        days = int(s[:-1])
        return int((now - timedelta(days=days)).timestamp())
    try:
        dt = dateparser.parse(s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def participant_by_puuid(match: Dict[str, Any], puuid: str) -> Dict[str, Any]:
    for p in match["info"]["participants"]:
        if p["puuid"] == puuid:
            return p
    raise KeyError("PUUID not in match participants")


def cs_from_frame(pf: Dict[str, Any]) -> int:
    return int(pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0))


def find_frame_at(timeline: Dict[str, Any], ms: int) -> Dict[str, Any]:
    frames = timeline["info"]["frames"]
    closest = min(frames, key=lambda f: abs(f.get("timestamp", 0) - ms))
    return closest


def lane_opponent_id(match: Dict[str, Any], timeline: Dict[str, Any], pid: int) -> Optional[int]:
    parts = match["info"]["participants"]
    me = next(p for p in parts if p["participantId"] == pid)
    my_team = me["teamId"]
    my_pos = me.get("teamPosition")
    if my_pos and my_pos != "UTILITY" and my_pos != "":
        enemies = [p for p in parts if p["teamId"] != my_team and p.get("teamPosition") == my_pos]
        if enemies:
            return enemies[0]["participantId"]
    # fallback: proximity 02:00–10:00
    frames = [f for f in timeline["info"]["frames"] if 120*MS <= f.get("timestamp", 0) <= 600*MS]
    dists: Dict[int, List[float]] = defaultdict(list)
    for f in frames:
        pfs = f.get("participantFrames", {})
        mepf = pfs.get(str(pid)) or pfs.get(pid) or {}
        mp = mepf.get("position") or {}
        mx, my = mp.get("x"), mp.get("y")
        if mx is None or my is None:
            continue
        for eid in range(1, 11):
            if eid == pid:
                continue
            epf = pfs.get(str(eid)) or pfs.get(eid) or {}
            ep = epf.get("position") or {}
            ex, ey = ep.get("x"), ep.get("y")
            if ex is None or ey is None:
                continue
            d = ((mx - ex) ** 2 + (my - ey) ** 2) ** 0.5
            dists[eid].append(d)
    if not dists:
        return None
    # choose enemy with min median distance
    best = None
    best_val = float("inf")
    for eid, vals in dists.items():
        part = next(p for p in parts if p["participantId"] == eid)
        if part["teamId"] == me["teamId"]:
            continue
        med = median(vals)
        if med < best_val:
            best_val = med
            best = eid
    return best


def compute_metrics(match: Dict[str, Any], timeline: Dict[str, Any], puuid: str) -> Dict[str, Any]:
    info = match.get("info", {})
    parts = info.get("participants", [])
    mep = participant_by_puuid(match, puuid)
    pid = mep["participantId"]
    my_team = mep["teamId"]
    role = mep.get("teamPosition") or None
    champion_id = int(mep.get("championId", 0))
    queue_id = int(info.get("queueId", 0))
    patch = str(info.get("gameVersion", "")).split(" ")[0]
    game_creation_ms = int(info.get("gameCreation", 0))
    game_duration_s = int(info.get("gameDuration", 0))

    # Timeline based metrics
    f10 = find_frame_at(timeline, 10 * 60 * MS)
    f14 = find_frame_at(timeline, 14 * 60 * MS)
    pf10 = f10.get("participantFrames", {}).get(str(pid), {})
    pf14 = f14.get("participantFrames", {}).get(str(pid), {})
    cs10 = cs_from_frame(pf10)
    cs14 = cs_from_frame(pf14)
    csmin10 = round(cs10 / 10.0, 2)
    csmin14 = round(cs14 / 14.0, 2)

    # Opponent mapping and diffs
    opp_id = lane_opponent_id(match, timeline, pid)
    gd10 = xpd10 = 0
    if opp_id:
        opp10 = f10.get("participantFrames", {}).get(str(opp_id), {})
        gd10 = int((pf10.get("totalGold") or 0) - (opp10.get("totalGold") or 0))
        xpd10 = int((pf10.get("xp") or 0) - (opp10.get("xp") or 0))

    # DL14 and events-derived metrics
    dl14 = 1
    ctrl_wards_pre14 = 0
    team_kills_pre14 = 0
    my_kills_pre14 = 0
    my_assists_pre14 = 0
    first_recall_s: Optional[int] = None
    for frame in timeline.get("info", {}).get("frames", []):
        for ev in frame.get("events", []) or []:
            ts = int(ev.get("timestamp", 0))
            if ev.get("type") == "CHAMPION_KILL":
                if ts < 14 * 60 * MS:
                    killer = ev.get("killerId")
                    victim = ev.get("victimId")
                    assists = ev.get("assistingParticipantIds") or []
                    # team kills
                    if killer and 1 <= killer <= 10:
                        kp = next((p for p in parts if p["participantId"] == killer), None)
                        if kp and kp["teamId"] == my_team:
                            team_kills_pre14 += 1
                    if victim == pid:
                        dl14 = 0
                    if killer == pid:
                        my_kills_pre14 += 1
                    if pid in assists:
                        my_assists_pre14 += 1
            elif ev.get("type") == "ITEM_PURCHASED":
                if ev.get("participantId") == pid:
                    if ts > 100 * 1000 and first_recall_s is None:
                        first_recall_s = int(ts / 1000)
                    if ts < 14 * 60 * 1000:
                        if int(ev.get("itemId") or 0) == 2055:
                            ctrl_wards_pre14 += 1
            elif ev.get("type") == "WARD_PLACED":
                if ts < 14 * 60 * 1000 and ev.get("creatorId") == pid and ev.get("wardType") == "CONTROL_WARD":
                    # we track placed separately via WARD_PLACED further if needed
                    pass

    kp_early = 0.0
    if team_kills_pre14 > 0:
        kp_early = round((my_kills_pre14 + my_assists_pre14) / team_kills_pre14 * 100.0, 1)

    row = {
        "puuid": puuid,
        "queue_id": queue_id,
        "patch": patch,
        "role": role,
        "champion_id": champion_id,
        "dl14": dl14,
        "cs10": cs10,
        "cs14": cs14,
        "csmin10": csmin10,
        "csmin14": csmin14,
        "gd10": gd10,
        "xpd10": xpd10,
        "first_recall_s": first_recall_s or 0,
        "ctrl_wards_pre14": ctrl_wards_pre14,
        "kp_early": kp_early,
        "game_creation_ms": game_creation_ms,
    }
    return row


def ingest_and_compute_recent(
    rc: RiotClient,
    store: Store,
    puuid: str,
    since: Optional[str] = None,
    count: int = 20,
    queue_filter: Optional[int] = None,
) -> int:
    start_time = _parse_since(since)
    seen = store.seen_match_ids()
    ids = rc.match_ids_by_puuid(puuid, start=0, count=count, start_time=start_time)
    ingested = 0
    for mid in ids:
        if mid in seen:
            continue
        match = rc.get_match(mid)
        info = match.get("info", {})
        queue_id = int(info.get("queueId", 0))
        if queue_filter is not None and queue_id != queue_filter:
            continue
        # skip remakes
        if int(info.get("gameDuration", 0)) < 300:
            continue
        timeline = rc.get_timeline(mid)

        mep = participant_by_puuid(match, puuid)
        role = mep.get("teamPosition") or None
        champion_id = int(mep.get("championId", 0))
        patch = str(info.get("gameVersion", "")).split(" ")[0]
        game_creation_ms = int(info.get("gameCreation", 0))
        game_duration_s = int(info.get("gameDuration", 0))

        store.upsert_match_raw(
            match_id=mid,
            puuid=puuid,
            queue_id=queue_id,
            game_creation_ms=game_creation_ms,
            game_duration_s=game_duration_s,
            patch=patch,
            role=role,
            champion_id=champion_id,
            raw_json=json.dumps(match),
        )
        store.upsert_timeline_raw(mid, json.dumps(timeline))

        # Frame + events extraction (subset for now)
        frames_rows: List[Tuple] = []
        events_rows: List[Tuple] = []
        for fr in timeline.get("info", {}).get("frames", []):
            ts = int(fr.get("timestamp", 0))
            pfs = fr.get("participantFrames", {}) or {}
            for k, pf in pfs.items():
                pid = int(k)
                total_gold = int(pf.get("totalGold") or 0)
                xp = int(pf.get("xp") or 0)
                cs = int((pf.get("minionsKilled") or 0) + (pf.get("jungleMinionsKilled") or 0))
                current_gold = int(pf.get("currentGold") or 0)
                pos = pf.get("position") or {}
                x = float(pos.get("x")) if pos.get("x") is not None else None
                y = float(pos.get("y")) if pos.get("y") is not None else None
                frames_rows.append((mid, ts, pid, total_gold, xp, cs, current_gold, x, y))
            for ev in fr.get("events", []) or []:
                events_rows.append(
                    (
                        mid,
                        int(ev.get("timestamp", 0)),
                        ev.get("type"),
                        int(ev.get("participantId")) if ev.get("participantId") is not None else None,
                        int(ev.get("killerId")) if ev.get("killerId") is not None else None,
                        int(ev.get("victimId")) if ev.get("victimId") is not None else None,
                        int(ev.get("itemId")) if ev.get("itemId") is not None else None,
                        ev.get("wardType"),
                    )
                )
        if frames_rows:
            store.insert_frames(frames_rows)
        if events_rows:
            store.insert_events(events_rows)

        row = compute_metrics(match, timeline, puuid)
        row["match_id"] = mid
        store.upsert_metrics(mid, row)
        # Compute extras (without Data Dragon; mythic/two-item may be 0)
        # Lazy import to avoid circular dependency
        from .metrics_extras import compute_extras
        extras = compute_extras(match, timeline, None, puuid)
        ex_row = {"match_id": mid, **extras["extras_row"]}
        store.upsert_metrics_extras(mid, ex_row)
        ingested += 1
    return ingested
