from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, HTTPException

from ..deps import config as get_cfg, save_config as save_cfg
from core.store import Store


router = APIRouter()


HUMAN_META = {
    "CS10": {"name": "CS by 10:00", "unit": "count"},
    "CS14": {"name": "CS by 14:00", "unit": "count"},
    "DL14": {"name": "No deaths until 14:00", "unit": "rate"},
    "GD10": {"name": "Gold lead @10", "unit": "gold"},
    "XPD10": {"name": "XP lead @10", "unit": "xp"},
    "CtrlWardsPre14": {"name": "Control wards before 14:00", "unit": "count"},
    "FirstRecall": {"name": "First recall time", "unit": "time"},
    "KPEarly": {"name": "Kill participation before 14:00", "unit": "rate"},
}

@router.get("/metrics/rolling")
def metrics_rolling(
    windows: str = Query("5,10"),
    days: str = Query("30"),
    segment: Optional[str] = Query(None),
    queue: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    champion: Optional[int] = Query(None),
    patch: Optional[str] = Query(None),
):
    cfg = get_cfg()
    puuid = cfg.get("player", {}).get("puuid")
    store = Store()
    cfg_queue = (cfg.get("player", {}).get("track_queues") or [None])[0]
    # If any segment filter is specified, compute on-the-fly; otherwise use cached windows for the configured queue
    use_dynamic = any(v is not None and v != "" for v in [queue, role, champion, patch])
    out: Dict[str, Dict[str, Any]] = {}
    import sqlite3, time
    from core.windows import value_of as w_value_of, ewma as w_ewma, sparkline as w_sparkline, summarize as w_summarize
    counts = [int(x) for x in (windows.split(',') if windows else []) if x]
    days_list = [int(x) for x in (days.split(',') if days else []) if x]

    if not use_dynamic:
        key = f"puuid:{puuid}:queue:{cfg_queue or 'any'}"
        with store.connect() as con:
            rows = con.execute(
                "SELECT metric, window_type, window_value, value, n, trend, spark FROM windows WHERE key=?",
                (key,),
            ).fetchall()
        for r in rows:
            metric, wtype, wval, val, n, trend, spark = r
            out.setdefault(metric, {}).setdefault(wtype, {})[int(wval)] = {
                "value": val,
                "n": int(n),
                "trend": trend,
                "spark": spark,
            }
    else:
        # Build filtered rows and compute windows
        with store.connect() as con:
            con.row_factory = sqlite3.Row
            q = "SELECT * FROM metrics WHERE puuid=?"
            params: list[Any] = [puuid]
            if queue is not None and queue != -1:
                q += " AND queue_id=?"
                params.append(queue)
            if role:
                q += " AND role=?"
                params.append(role)
            if champion is not None:
                q += " AND champion_id=?"
                params.append(champion)
            if patch:
                q += " AND patch=?"
                params.append(patch)
            q += " ORDER BY game_creation_ms DESC"
            rows_all = [dict(r) for r in con.execute(q, params).fetchall()]
        metrics_list = cfg.get("metrics", {}).get("primary", [])
        for m in metrics_list:
            # count windows
            for w in counts:
                subset = rows_all[:w]
                series = w_value_of(m, list(reversed(subset)))
                val = w_summarize(w_value_of(m, subset))
                out.setdefault(m, {}).setdefault("count", {})[int(w)] = {
                    "value": float(val),
                    "n": len(subset),
                    "trend": float(round(w_ewma(series), 2)) if series else 0.0,
                    "spark": w_sparkline(series[-8:]),
                }
            # day windows
            now_ms = int(time.time() * 1000)
            for d in days_list:
                cutoff = now_ms - d * 24 * 3600 * 1000
                subset = [r for r in rows_all if r["game_creation_ms"] >= cutoff]
                series = w_value_of(m, list(reversed(subset)))
                val = w_summarize(w_value_of(m, subset))
                out.setdefault(m, {}).setdefault("days", {})[int(d)] = {
                    "value": float(val),
                    "n": len(subset),
                    "trend": float(round(w_ewma(series), 2)) if series else 0.0,
                    "spark": w_sparkline(series[-8:]),
                }

    # Also include short value arrays for charts (last up to 8)
    import sqlite3
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        q = "SELECT * FROM metrics WHERE puuid=?"
        params: list[Any] = [puuid]
        q_queue = (None if (use_dynamic and queue == -1) else (queue if use_dynamic else cfg_queue))
        if q_queue is not None:
            q += " AND queue_id=?"
            params.append(q_queue)
        if use_dynamic and role:
            q += " AND role=?"
            params.append(role)
        if use_dynamic and champion is not None:
            q += " AND champion_id=?"
            params.append(champion)
        if use_dynamic and patch:
            q += " AND patch=?"
            params.append(patch)
        q += " ORDER BY game_creation_ms DESC LIMIT 50"
        mets = con.execute(q, params).fetchall()
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

    # Units map included for client formatting
    units = {m: HUMAN_META.get(m, {}).get("unit") for m in metrics_list}
    return {"ok": True, "data": {"windows": out, "series": windows_payload, "summary": summary, "units": units}}


@router.get("/targets")
def get_targets():
    cfg = get_cfg()
    weights = cfg.get("metrics", {}).get("weights", {})
    manual_targets = cfg.get("metrics", {}).get("targets", {})
    goals_cfg = cfg.get("goals", {})
    conservative_floor = goals_cfg.get("conservative_floor", {"CS10": 55, "GD10": -200})
    step_min = goals_cfg.get("step_min", {"CS10": 3, "GD10": 50})
    ratchet_inc = goals_cfg.get("ratchet_inc", {"CS10": 3, "GD10": 50})

    puuid = cfg.get("player", {}).get("puuid")
    store = Store()
    # Determine context: configured tracked queue and resolved role from recent matches
    q_in = (cfg.get("player", {}).get("track_queues") or [None])[0]
    q = None if q_in == -1 else q_in
    ranked = set(int(x) for x in (cfg.get("gis", {}).get("rankedQueues") or [420, 440]))
    # Resolve dominant role from recent ranked matches in this queue (if any)
    resolved_role = None
    try:
        import sqlite3
        with store.connect() as con:
            con.row_factory = sqlite3.Row
            inner = "SELECT role FROM matches WHERE puuid=? AND queue_id IN (%s)" % (",".join([str(x) for x in ranked]))
            params = [puuid]
            if q is not None:
                inner += " AND queue_id=?"
                params.append(q)
            inner += " ORDER BY game_creation_ms DESC LIMIT 20"
            sql = f"SELECT role, COUNT(1) as n FROM ({inner}) t GROUP BY role ORDER BY n DESC LIMIT 1"
            row = con.execute(sql, params).fetchone()
            if row and row["role"]:
                resolved_role = row["role"]
    except Exception:
        pass

    # Load all metric rows in context (ranked + queue + role)
    import sqlite3, statistics as stats
    with store.connect() as con:
        con.row_factory = sqlite3.Row
        qbase = "SELECT * FROM metrics WHERE puuid=?"
        params: list[Any] = [puuid]
        if q is not None:
            qbase += " AND queue_id=?"
            params.append(q)
        # role filter if resolved
        if resolved_role:
            qbase += " AND role=?"
            params.append(resolved_role)
        # ranked-only
        if ranked:
            qbase += " AND queue_id IN (%s)" % (",".join([str(x) for x in ranked]))
        qbase += " ORDER BY game_creation_ms DESC"
        rows_all = con.execute(qbase, params).fetchall()

    sample_n = len(rows_all)
    metrics_list = cfg.get("metrics", {}).get("primary", [])

    def vals(metric: str, rs):
        arr = []
        for r in rs:
            if metric == "DL14": arr.append(float(r["dl14"]))
            elif metric == "CS10": arr.append(float(r["cs10"]))
            elif metric == "CS14": arr.append(float(r["cs14"]))
            elif metric == "GD10": arr.append(float(r["gd10"]))
            elif metric == "XPD10": arr.append(float(r["xpd10"]))
            elif metric == "CtrlWardsPre14": arr.append(float(r["ctrl_wards_pre14"]))
            elif metric == "KPEarly": arr.append(float(r["kp_early"]))
            elif metric == "FirstRecall": arr.append(float(r["first_recall_s"]))
        return arr

    # Load ratchet state
    import json
    key_state = f"goals:ratchet:{puuid}"
    try:
        raw = store.get_meta(key_state)
        state = json.loads(raw) if raw else {"targets": {}}
    except Exception:
        state = {"targets": {}}
    last_targets: Dict[str, float] = dict(state.get("targets") or {})
    # Sanitize legacy mis-scaled targets: ensure DL14 (rate) is stored as a fraction 0..1
    try:
        if "DL14" in last_targets:
            v = float(last_targets.get("DL14") or 0.0)
            if v > 1.5:  # clearly percent-like, fix to fraction
                last_targets["DL14"] = round(v / 100.0, 4)
    except Exception:
        pass

    by_metric: Dict[str, Dict[str, Any]] = {}

    for m in metrics_list:
        series_all = vals(m, rows_all)
        # personal baseline = median of last up to 20 samples
        if series_all:
            baseline = stats.median(series_all[:20])
        else:
            baseline = 0.0
        # cohort p70 not available yet; leave as None
        cohort_p70 = None
        # Defaults
        manual = (manual_targets.get(m, {}) or {}).get("manual_floor")
        # Manual overrides are stored canonically: for rate metrics as fractions 0..1.
        # Convert to internal unit for computation: DL14 already 0..1; KPEarly etc. use 0..100 in storage.
        unit = (HUMAN_META.get(m, {}) or {}).get("unit", "count")
        if manual is not None and unit == "rate" and m != "DL14":
            try:
                manual = float(manual) * 100.0
            except Exception:
                manual = manual
        base_floor = float(conservative_floor.get(m, 0) or 0)
        step = float(step_min.get(m, 0) or 0)
        inc = float(ratchet_inc.get(m, step) or step)
        # Build default target by sample size
        if manual is not None:
            default_target = float(manual)
        else:
            if sample_n < 8:
                default_target = max(base_floor, baseline + step)
            else:
                if cohort_p70 is not None:
                    default_target = round(0.5 * baseline + 0.5 * float(cohort_p70))
                else:
                    default_target = baseline + step
        # Ratchet using last 5 matches against last target (or default)
        last_target = float(last_targets.get(m, default_target))
        # If manual override present and higher (or lower for time), respect and reset base
        unit = (HUMAN_META.get(m, {}) or {}).get("unit", "count")
        last5 = series_all[:5]
        achieved = 0
        # For time metrics, lower is better
        if unit == "time":
            # If manual provided and lower than last_target, keep the lower manual without lowering ratchet automatically
            if manual is not None:
                try:
                    manual_f = float(manual)
                    last_target = min(last_target, manual_f)
                except Exception:
                    pass
            for v in last5:
                try:
                    if v <= last_target:
                        achieved += 1
                except Exception:
                    pass
            if achieved >= 3:
                # Lower target slightly (faster recall) by inc
                last_target = max(0.0, last_target - inc)
        else:
            # If manual provided and higher than last_target, raise baseline to manual immediately (no auto-lower)
            if manual is not None:
                try:
                    manual_f = float(manual)
                    if manual_f > last_target:
                        last_target = manual_f
                except Exception:
                    pass
            # For rates (0..100), values are stored as 0..100 except DL14 which is 0..1
            for v in last5:
                try:
                    if m == "DL14":
                        vv = float(v)  # already 0..1
                        tt = float(last_target)
                    else:
                        vv = float(v)
                        tt = float(last_target)
                    if vv >= tt:
                        achieved += 1
                except Exception:
                    pass
            if achieved >= 3:
                last_target = last_target + inc
        # Persist back (do not auto-lower targets)
        if m not in last_targets or last_targets.get(m) != last_target:
            # Persist in canonical units: DL14 as 0..1 fraction; other rates (e.g., KPEarly) use their series units (0..100)
            if unit == "rate" and m == "DL14":
                last_targets[m] = float(last_target)
            else:
                last_targets[m] = float(last_target)

        # Compute p50/p75 for context (based on all rows)
        p50 = (stats.median(series_all) if series_all else None)
        p75 = None
        if series_all:
            srt = sorted(series_all)
            p75 = srt[int(0.75 * (len(srt) - 1))]

        meta = HUMAN_META.get(m, {"name": m, "unit": "count"})
        t_out: Optional[float] = last_target
        # Normalize rates to fractions 0..1 for UI formatting where needed.
        # DL14 already 0..1; others like KPEarly use 0..100 in metrics storage.
        if meta["unit"] == "rate" and m != "DL14":
            p50 = (p50 / 100.0) if (p50 is not None) else None
            p75 = (p75 / 100.0) if (p75 is not None) else None
            t_out = (t_out / 100.0) if (t_out is not None) else None
        # Progress ratio toward target (0..1), using last-5 average where available
        prog: Optional[float] = None
        try:
            last5_vals = series_all[:5]
            v = (sum(last5_vals) / len(last5_vals)) if last5_vals else None
            if v is not None and t_out is not None and t_out != 0:
                if meta["unit"] == "time":
                    prog = max(0.0, min(1.0, (t_out or 0.0) / (v or 1.0)))
                elif meta["unit"] == "rate":
                    # Ensure v is as fraction (convert if KPEarly-style 0..100)
                    vv = (v / 100.0) if (m != "DL14") else v
                    prog = max(0.0, min(1.0, vv / (t_out or 1.0)))
                else:
                    prog = max(0.0, min(1.0, (v or 0.0) / (t_out or 1.0)))
        except Exception:
            prog = None
        by_metric[m] = {"name": meta["name"], "unit": meta["unit"], "target": t_out, "p50": p50, "p75": p75, "progress_ratio": prog}

    # Save ratchet state
    try:
        store.set_meta(key_state, json.dumps({"targets": last_targets}))
    except Exception:
        pass

    # Provisional if limited sample so far
    provisional = sample_n < 8
    return {"ok": True, "data": {"provisional": provisional, "metrics": by_metric, "weights": weights}}


@router.delete("/targets/overrides")
def reset_overrides():
    cfg = get_cfg()
    # Clear any manual targets/overrides
    try:
        if isinstance(cfg.get("metrics"), dict):
            cfg["metrics"]["targets"] = {}
        else:
            cfg.setdefault("metrics", {})["targets"] = {}
        save_cfg(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "WRITE_FAILED", "message": str(e)})
    return {"ok": True, "data": True}


@router.post("/targets/override")
def set_target_override(payload: Dict[str, Any]):
    """Force-set a manual target override for a metric.

    Payload: { metric: string, value: number|string }
    For rate metrics, accepts 65, "65%", or 0.65 and stores 0.65.
    """
    metric = (payload or {}).get("metric")
    raw_val = (payload or {}).get("value")
    if not metric or raw_val is None:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "metric and value are required"})
    meta = HUMAN_META.get(metric, {"unit": "count"})

    def _parse_rate(v: Any) -> float:
        if isinstance(v, str):
            s = v.strip()
            if s.endswith("%"):
                s = s[:-1]
            try:
                n = float(s)
            except Exception:
                raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "Enter a number like 65 or 0.65"})
        else:
            try:
                n = float(v)
            except Exception:
                raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "Enter a number like 65 or 0.65"})
        frac = n / 100.0 if n > 1.0 else n
        if frac < 0 or frac > 1:
            raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "Rate must be 0–100% (e.g., 65 or 0.65)"})
        return float(frac)

    # Canonicalize by unit
    if meta.get("unit") == "rate":
        # Store fraction 0..1 for all rate metrics including DL14
        v_canon = _parse_rate(raw_val)
        # For internal ratchet logic using 0..100 (except DL14), we adjust during computation
    else:
        try:
            v_canon = float(raw_val)
        except Exception:
            raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "value must be a number"})

    cfg = get_cfg()
    cfg.setdefault("metrics", {}).setdefault("targets", {})
    prev = (cfg["metrics"]["targets"].get(metric) or {})
    prev["manual_floor"] = v_canon
    cfg["metrics"]["targets"][metric] = prev
    try:
        save_cfg(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "WRITE_FAILED", "message": str(e)})
    # Return current /targets shape for convenience
    return get_targets()


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
