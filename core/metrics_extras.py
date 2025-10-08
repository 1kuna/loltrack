from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .metrics import MS, participant_by_puuid, find_frame_at, lane_opponent_id


def _minutes(duration_s: int) -> float:
    return max(1.0, (duration_s or 1) / 60.0)


def _participant_team_kills(match: Dict[str, Any], team_id: int) -> int:
    total = 0
    for p in match.get("info", {}).get("participants", []):
        if int(p.get("teamId") or 0) == team_id:
            total += int(p.get("kills") or 0)
    return total


def _obj_participation(match: Dict[str, Any], timeline: Dict[str, Any], pid: int, my_team: int) -> float:
    info = match.get("info", {})
    # count team objectives (drag/herald/baron + towers) for my team
    team_obj = 0
    my_contrib = 0
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            typ = ev.get("type")
            if typ == "ELITE_MONSTER_KILL":
                mtype = ev.get("monsterType")
                if mtype in ("DRAGON", "RIFTHERALD", "BARON_NASHOR"):
                    killer = int(ev.get("killerId") or 0)
                    # map killer to team
                    kteam = None
                    for p in info.get("participants", []):
                        if int(p.get("participantId") or 0) == killer:
                            kteam = int(p.get("teamId") or 0)
                            break
                    if kteam == my_team:
                        team_obj += 1
                        assists = ev.get("assistingParticipantIds") or []
                        if killer == pid or pid in assists:
                            my_contrib += 1
            elif typ == "BUILDING_KILL":
                btype = ev.get("buildingType")
                if btype == "TOWER_BUILDING":
                    # team inference from killerId
                    killer = int(ev.get("killerId") or 0)
                    kteam = None
                    for p in info.get("participants", []):
                        if int(p.get("participantId") or 0) == killer:
                            kteam = int(p.get("teamId") or 0)
                            break
                    if kteam == my_team:
                        team_obj += 1
                        assists = ev.get("assistingParticipantIds") or []
                        if killer == pid or pid in assists:
                            my_contrib += 1
    if team_obj <= 0:
        return 0.0
    return round(my_contrib / team_obj * 100.0, 1)


def _items_with_timings(timeline: Dict[str, Any], pid: int) -> List[Dict[str, int]]:
    items: List[Dict[str, int]] = []
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            if ev.get("type") == "ITEM_PURCHASED" and int(ev.get("participantId") or 0) == pid:
                ts = int(int(ev.get("timestamp") or 0) / 1000)
                iid = int(ev.get("itemId") or 0)
                if iid:
                    items.append({"id": iid, "t": ts})
    return items


def _is_mythic_item(dd_item: Dict[str, Any]) -> bool:
    # Heuristic: description contains 'rarityMythic' or 'Mythic Passive'
    desc = (dd_item or {}).get("description") or ""
    return ("rarityMythic" in desc) or ("Mythic Passive" in desc) or ("Mythic" in desc)


def _item_cost(dd_item: Dict[str, Any]) -> int:
    gold = (dd_item or {}).get("gold") or {}
    return int(gold.get("total") or 0)


def compute_extras(
    match: Dict[str, Any],
    timeline: Dict[str, Any],
    ddragon_items: Dict[str, Any] | None,
    puuid: str,
) -> Dict[str, Any]:
    info = match.get("info", {})
    mep = participant_by_puuid(match, puuid)
    pid = int(mep.get("participantId") or 0)
    my_team = int(mep.get("teamId") or 0)
    duration_s = int(info.get("gameDuration") or 0)

    minutes = _minutes(duration_s)
    dpm = float(mep.get("totalDamageDealtToChampions") or 0) / minutes
    gpm = float(mep.get("goldEarned") or 0) / minutes
    csm = float((mep.get("totalMinionsKilled") or 0) + (mep.get("neutralMinionsKilled") or 0)) / minutes
    dmg_obj = int(mep.get("damageDealtToObjectives") or 0)
    dmg_turrets = int(mep.get("damageDealtToTurrets") or 0)
    dmg_to_champs = int(mep.get("totalDamageDealtToChampions") or 0)
    dmg_taken = int(mep.get("totalDamageTaken") or 0)
    vision_per_min = float(mep.get("visionScore") or 0) / minutes
    wards_placed = int(mep.get("wardsPlaced") or 0)
    wards_killed = int(mep.get("wardsKilled") or 0)

    # KP
    k = int(mep.get("kills") or 0)
    a = int(mep.get("assists") or 0)
    team_kills = _participant_team_kills(match, my_team)
    kp = round(((k + a) / team_kills) * 100.0, 1) if team_kills > 0 else 0.0

    # Diffs @ 10/@15 via frames
    f10 = find_frame_at(timeline, 10 * 60 * MS)
    f15 = find_frame_at(timeline, 15 * 60 * MS)
    opp_id = lane_opponent_id(match, timeline, pid)
    gd10 = xpd10 = gd15 = xpd15 = 0
    pf10 = f10.get("participantFrames", {}).get(str(pid), {})
    pf15 = f15.get("participantFrames", {}).get(str(pid), {})
    if opp_id:
        opp10 = f10.get("participantFrames", {}).get(str(opp_id), {})
        opp15 = f15.get("participantFrames", {}).get(str(opp_id), {})
        gd10 = int((pf10.get("totalGold") or 0) - (opp10.get("totalGold") or 0))
        xpd10 = int((pf10.get("xp") or 0) - (opp10.get("xp") or 0))
        gd15 = int((pf15.get("totalGold") or 0) - (opp15.get("totalGold") or 0))
        xpd15 = int((pf15.get("xp") or 0) - (opp15.get("xp") or 0))

    # Objective participation
    obj_participation = _obj_participation(match, timeline, pid, my_team)

    # Items and timings
    items = _items_with_timings(timeline, pid)
    mythic_at_s: Optional[int] = None
    two_item_at_s: Optional[int] = None
    trinket_swap_at_s: Optional[int] = None
    if ddragon_items:
        # Build a dict of id -> item meta
        data = (ddragon_items.get("data") or {})
        seen_big = 0
        first_trinket: Optional[int] = None
        for it in sorted(items, key=lambda x: x["t"]):
            meta = data.get(str(it["id"])) or {}
            if mythic_at_s is None and _is_mythic_item(meta):
                mythic_at_s = it["t"]
            # consider big item threshold ~2500g
            if _item_cost(meta) >= 2500:
                seen_big += 1
                if seen_big == 2 and two_item_at_s is None:
                    two_item_at_s = it["t"]
            # Trinket swap detection
            iid = int(it["id"])
            if iid in (3340, 3363, 3364):
                if first_trinket is None and iid == 3340:
                    first_trinket = iid
                elif iid in (3363, 3364) and trinket_swap_at_s is None:
                    trinket_swap_at_s = it["t"]

    # Roam distance pre-14: simple path length before 14m
    def _path_len_before(ts_limit_ms: int) -> float:
        pts: List[Tuple[float, float]] = []
        for fr in timeline.get("info", {}).get("frames", []) or []:
            ts = int(fr.get("timestamp") or 0)
            if ts > ts_limit_ms:
                break
            pf = fr.get("participantFrames", {}).get(str(pid), {})
            pos = pf.get("position") or {}
            x = pos.get("x")
            y = pos.get("y")
            if x is not None and y is not None:
                pts.append((float(x), float(y)))
        dist = 0.0
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            dist += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return dist

    roam_distance_pre14 = _path_len_before(14 * 60 * 1000)

    # Ward clears pre-14 and total, plates pre-14, objective proximity (within ~2500 units of event)
    ward_clears_pre14 = 0
    ward_clears_total = 0
    plates_pre14 = 0
    obj_near = 0
    # helper to get my position around a timestamp
    def _pos_near(ts: int) -> Optional[Tuple[float, float]]:
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
    for fr in timeline.get("info", {}).get("frames", []) or []:
        for ev in fr.get("events", []) or []:
            ts = int(ev.get("timestamp") or 0)
            typ = ev.get("type")
            if typ == "WARD_KILL":
                if int(ev.get("killerId") or 0) == pid:
                    ward_clears_total += 1
                    if ts < 14 * 60 * 1000:
                        ward_clears_pre14 += 1
            elif typ == "TURRET_PLATE_DESTROYED":
                # credit if killerId is me; if event lacks killer, approximate with proximity
                if int(ev.get("killerId") or 0) == pid or (lambda: (
                    (lambda mp, ep: (mp is not None and ep is not None and ((mp[0]-ep[0])**2 + (mp[1]-ep[1])**2) ** 0.5 <= 2000))(
                        _pos_near(ts),
                        (lambda p: (float(p.get('x')), float(p.get('y'))) if p else None)(ev.get("position"))
                    )
                ))():
                    if ts < 14 * 60 * 1000:
                        plates_pre14 += 1
            elif typ in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
                # count proximity for my team objectives only
                kteam = None
                killer = int(ev.get("killerId") or 0)
                for p in match.get("info", {}).get("participants", []) or []:
                    if int(p.get("participantId") or 0) == killer:
                        kteam = int(p.get("teamId") or 0)
                        break
                if kteam == my_team:
                    mp = _pos_near(ts)
                    ep = ev.get("position") or {}
                    ex = ep.get("x"); ey = ep.get("y")
                    if mp and ex is not None and ey is not None:
                        dx = mp[0] - float(ex)
                        dy = mp[1] - float(ey)
                        if (dx * dx + dy * dy) ** 0.5 <= 2500:
                            obj_near += 1

    # Overview fields for drawer
    overview = {
        "k": k,
        "d": int(mep.get("deaths") or 0),
        "a": a,
        "kda": round((k + a) / max(1, int(mep.get("deaths") or 0)), 2),
        "kp": kp,
        "dpm": round(dpm, 1),
        "gpm": round(gpm, 1),
        "csm": round(csm, 2),
        "gd10": gd10,
        "gd15": gd15,
        "xpd10": xpd10,
        "xpd15": xpd15,
        "dmgToChamps": dmg_to_champs,
        "dmgTaken": dmg_taken,
        "dmgObj": dmg_obj,
        "dmgTurrets": dmg_turrets,
        "visionPerMin": round(vision_per_min, 2),
        "wardsPlaced": wards_placed,
        "wardsKilled": wards_killed,
        "items": items,
        "mythicAtS": mythic_at_s,
        "twoItemAtS": two_item_at_s,
        "trinketSwapAtS": trinket_swap_at_s,
        "objParticipation": obj_participation,
        "roamDistancePre14": roam_distance_pre14,
        "wardClearsPre14": ward_clears_pre14,
        "wardClears": ward_clears_total,
        "platesPre14": plates_pre14,
        "objNear": obj_near,
    }
    # extras row for caching
    extras_row = {
        "puuid": puuid,
        "dpm": round(dpm, 1),
        "gpm": round(gpm, 1),
        "obj_participation": obj_participation,
        "dmg_obj": dmg_obj,
        "dmg_turrets": dmg_turrets,
        "mythic_at_s": mythic_at_s or 0,
        "two_item_at_s": two_item_at_s or 0,
        "vision_per_min": round(vision_per_min, 2),
        "wards_placed": wards_placed,
        "wards_killed": wards_killed,
        "roam_distance_pre14": roam_distance_pre14,
    }
    return {"overview": overview, "extras_row": extras_row}
