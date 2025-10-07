from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from ..deps import config as get_cfg
from loltrack.store import Store


router = APIRouter()


@router.get("/metrics/rolling")
def metrics_rolling(
    windows: str = Query("5,10,20"),
    days: str = Query("30,60"),
    segment: Optional[str] = Query(None),
):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    store = Store()
    queue = (cfg.get("player", {}).get("track_queues") or [None])[0]
    key = f"puuid:{puuid}:queue:{queue or 'any'}"
    with store.connect() as con:
        rows = con.execute(
            "SELECT metric, window_type, window_value, value, n, trend, spark FROM windows WHERE key=?",
            (key,),
        ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        metric, wtype, wval, val, n, trend, spark = r
        out.setdefault(metric, {}).setdefault(wtype, {})[int(wval)] = {
            "value": val,
            "n": int(n),
            "trend": trend,
            "spark": spark,
        }

    # Also include short value arrays for charts (last up to 8)
    import sqlite3
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        mets = con.execute(
            "SELECT * FROM metrics WHERE puuid=? AND (? IS NULL OR queue_id=?) ORDER BY game_creation_ms DESC LIMIT 50",
            (puuid, queue, queue),
        ).fetchall()
    metrics_list = cfg.get("metrics", {}).get("primary", [])
    def series(metric: str):
        vals = []
        for r in mets:
            if metric == "DL14": vals.append(float(r["dl14"]) * 100.0)
            elif metric == "CS10": vals.append(float(r["cs10"]))
            elif metric == "CS14": vals.append(float(r["cs14"]))
            elif metric == "GD10": vals.append(float(r["gd10"]))
            elif metric == "XPD10": vals.append(float(r["xpd10"]))
            elif metric == "CtrlWardsPre14": vals.append(float(r["ctrl_wards_pre14"]))
            elif metric == "KPEarly": vals.append(float(r["kp_early"]))
            elif metric == "FirstRecall": vals.append(float(r["first_recall_s"]))
        return list(reversed(vals))[-8:]

    windows_payload = {}
    for m in metrics_list:
        windows_payload[m] = {
            "values": series(m),
        }

    # Improvement index quick calc (median of last 10 vs baseline first 10)
    import statistics as stats
    def vals(metric: str, rs):
        arr = []
        for r in rs:
            if metric == "DL14": arr.append(float(r["dl14"]) * 100.0)
            elif metric == "CS10": arr.append(float(r["cs10"]))
            elif metric == "CS14": arr.append(float(r["cs14"]))
            elif metric == "GD10": arr.append(float(r["gd10"]))
            elif metric == "XPD10": arr.append(float(r["xpd10"]))
            elif metric == "CtrlWardsPre14": arr.append(float(r["ctrl_wards_pre14"]))
            elif metric == "KPEarly": arr.append(float(r["kp_early"]))
            elif metric == "FirstRecall": arr.append(float(r["first_recall_s"]))
        return arr
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        first10 = con.execute(
            "SELECT * FROM metrics WHERE puuid=? AND (? IS NULL OR queue_id=?) ORDER BY game_creation_ms ASC LIMIT 10",
            (puuid, queue, queue),
        ).fetchall()
        last10 = con.execute(
            "SELECT * FROM metrics WHERE puuid=? AND (? IS NULL OR queue_id=?) ORDER BY game_creation_ms DESC LIMIT 10",
            (puuid, queue, queue),
        ).fetchall()
    weights = cfg.get("metrics", {}).get("weights", {})
    metrics_list = cfg.get("metrics", {}).get("primary", [])

    def mad(arr: list[float]) -> float:
        if not arr:
            return 0.0
        med = stats.median(arr)
        return stats.median([abs(x - med) for x in arr])

    def eps_for(metric: str) -> float:
        return {
            "CS10": 1.0,
            "CS14": 1.0,
            "GD10": 50.0,
            "XPD10": 50.0,
            "CtrlWardsPre14": 0.5,
            "KPEarly": 5.0,
            "FirstRecall": 15.0,
            "DL14": 0.05,  # not used in z, kept for reserve
        }.get(metric, 1.0)

    score_sum = 0.0
    weight_sum = 0.0
    provisional = len(first10) < 10
    for m in metrics_list:
        b = vals(m, first10)
        c = vals(m, last10)
        if not c:
            continue
        if m == "DL14":
            rate_b = (sum(b) / len(b)) / 1.0 if b else 0.0  # b already 0..100; convert to 0..1
            rate_c = (sum(c) / len(c)) / 100.0 if c else 0.0
            if b:
                rate_b = (sum([x/100.0 for x in b]) / len(b))
            else:
                rate_b = 0.0
            rate_c = (sum([x/100.0 for x in c]) / len(c))
            score_m = max(-100.0, min(100.0, (rate_c - rate_b) * 200.0))
        else:
            baseline = stats.median(b) if b else 0.0
            current = stats.median(c) if c else 0.0
            robust_std = max(1.4826 * mad(b), eps_for(m))
            z = (current - baseline) / robust_std if robust_std > 0 else 0.0
            if m == "FirstRecall":
                z = -z
            score_m = max(-100.0, min(100.0, 50.0 * z))
        w = float(weights.get(m, 1.0))
        score_sum += w * score_m
        weight_sum += w
    summary = {"improvement_index": round(score_sum / weight_sum, 2) if weight_sum else 0.0, "provisional": provisional}

    return {"ok": True, "data": {"windows": out, "series": windows_payload, "summary": summary}}


@router.get("/targets")
def get_targets():
    cfg = get_cfg()
    weights = cfg.get("metrics", {}).get("weights", {})
    manual_targets = cfg.get("metrics", {}).get("targets", {})
    # Compute provisional/baseline when possible
    puuid = cfg.get("player", {}).get("puuid")
    store = Store()
    import sqlite3, statistics as stats
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM metrics WHERE puuid=? ORDER BY game_creation_ms ASC LIMIT 10",
            (puuid,),
        ).fetchall()
    metrics_list = cfg.get("metrics", {}).get("primary", [])
    def vals(metric: str):
        arr = []
        for r in rows:
            if metric == "DL14": arr.append(float(r["dl14"]))
            elif metric == "CS10": arr.append(float(r["cs10"]))
            elif metric == "CS14": arr.append(float(r["cs14"]))
            elif metric == "GD10": arr.append(float(r["gd10"]))
            elif metric == "XPD10": arr.append(float(r["xpd10"]))
            elif metric == "CtrlWardsPre14": arr.append(float(r["ctrl_wards_pre14"]))
            elif metric == "KPEarly": arr.append(float(r["kp_early"]))
            elif metric == "FirstRecall": arr.append(float(r["first_recall_s"]))
        return arr
    baseline_ok = len(rows) >= 10
    by_metric = {}
    for m in metrics_list:
        v = vals(m)
        p50 = stats.median(v) if v else None
        p75 = None
        if v:
            s = sorted(v)
            p75 = s[int(0.75 * (len(s)-1))]
        target = manual_targets.get(m, {}).get("manual_floor") if manual_targets.get(m, {}) else None
        if baseline_ok and p75 is not None:
            target = max(target or 0, p75)
        if target is None:
            target = 0
        by_metric[m] = {"target": target, "p50": p50, "p75": p75}
    return {"ok": True, "data": {"provisional": not baseline_ok, "by_metric": by_metric, "weights": weights}}


@router.get("/metrics/improvement-index")
def improvement_index():
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    if not puuid:
        return {"ok": True, "data": {"score": 0}}
    store = Store()
    queue = (cfg.get("player", {}).get("track_queues") or [None])[0]
    weights = cfg.get("metrics", {}).get("weights", {})
    # Baseline = first 10 games; last10 for current
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM metrics WHERE puuid=? AND (? IS NULL OR queue_id=?) ORDER BY game_creation_ms ASC LIMIT 10",
            (puuid, queue, queue),
        ).fetchall()
        last10 = con.execute(
            "SELECT * FROM metrics WHERE puuid=? AND (? IS NULL OR queue_id=?) ORDER BY game_creation_ms DESC LIMIT 10",
            (puuid, queue, queue),
        ).fetchall()
    import statistics as stats
    def vals(metric: str, rs):
        arr = []
        for r in rs:
            if metric == "DL14": arr.append(float(r["dl14"]) * 100.0)
            elif metric == "CS10": arr.append(float(r["cs10"]))
            elif metric == "CS14": arr.append(float(r["cs14"]))
            elif metric == "GD10": arr.append(float(r["gd10"]))
            elif metric == "XPD10": arr.append(float(r["xpd10"]))
            elif metric == "CtrlWardsPre14": arr.append(float(r["ctrl_wards_pre14"]))
            elif metric == "KPEarly": arr.append(float(r["kp_early"]))
            elif metric == "FirstRecall": arr.append(float(r["first_recall_s"]))
        return arr
    def mad(arr: list[float]) -> float:
        if not arr:
            return 0.0
        med = stats.median(arr)
        return stats.median([abs(x - med) for x in arr])
    def eps_for(metric: str) -> float:
        return {
            "CS10": 1.0,
            "CS14": 1.0,
            "GD10": 50.0,
            "XPD10": 50.0,
            "CtrlWardsPre14": 0.5,
            "KPEarly": 5.0,
            "FirstRecall": 15.0,
            "DL14": 0.05,
        }.get(metric, 1.0)
    metrics_list = cfg.get("metrics", {}).get("primary", [])
    score_sum = 0.0
    weight_sum = 0.0
    for m in metrics_list:
        b = vals(m, rows)
        c = vals(m, last10)
        if not c:
            continue
        if m == "DL14":
            rate_b = (sum([x/100.0 for x in b]) / len(b)) if b else 0.0
            rate_c = (sum([x/100.0 for x in c]) / len(c))
            score_m = max(-100.0, min(100.0, (rate_c - rate_b) * 200.0))
        else:
            baseline = stats.median(b) if b else 0.0
            current = stats.median(c) if c else 0.0
            robust_std = max(1.4826 * mad(b), eps_for(m))
            z = (current - baseline) / robust_std if robust_std > 0 else 0.0
            if m == "FirstRecall":
                z = -z
            score_m = max(-100.0, min(100.0, 50.0 * z))
        w = float(weights.get(m, 1.0))
        score_sum += w * score_m
        weight_sum += w
    score = round(score_sum / weight_sum, 2) if weight_sum else 0.0
    return {"ok": True, "data": {"score": score}}
