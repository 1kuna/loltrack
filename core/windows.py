from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

from .store import Store


def ewma(values: List[float], half_life_games: float = 10.0) -> float:
    if not values:
        return 0.0
    alpha = 1 - 0.5 ** (1 / half_life_games)
    s = values[0]
    for v in values[1:]:
        s = alpha * v + (1 - alpha) * s
    return s


BLOCKS = "▁▂▃▄▅▆▇"


def sparkline(values: List[float]) -> str:
    if not values:
        return ""
    vmin = min(values)
    vmax = max(values)
    if vmax - vmin < 1e-6:
        return BLOCKS[0] * len(values)
    out = []
    for v in values:
        idx = int((v - vmin) / (vmax - vmin) * (len(BLOCKS) - 1))
        out.append(BLOCKS[idx])
    return "".join(out)


def value_of(metric: str, rows: List[Dict[str, Any]]) -> List[float]:
    out: List[float] = []
    for r in rows:
        if metric == "DL14":
            out.append(float(r["dl14"]) * 100.0)
        elif metric == "CS10":
            out.append(float(r["cs10"]))
        elif metric == "CS14":
            out.append(float(r["cs14"]))
        elif metric == "GD10":
            out.append(float(r["gd10"]))
        elif metric == "XPD10":
            out.append(float(r["xpd10"]))
        elif metric == "FirstRecall":
            out.append(float(r["first_recall_s"]))
        elif metric == "CtrlWardsPre14":
            out.append(float(r["ctrl_wards_pre14"]))
        elif metric == "KPEarly":
            out.append(float(r["kp_early"]))
    return out


def summarize(values: List[float]) -> float:
    if not values:
        return 0.0
    # For rates, we already scaled to 100.
    return round(sum(values) / len(values), 2)


def rebuild_windows(store: Store, cfg: Dict[str, Any]) -> None:
    puuid = cfg["player"].get("puuid")
    if not puuid:
        return
    queue = (cfg["player"].get("track_queues") or [None])[0]
    rows_all = store.recent_metrics(puuid, queue)
    rows = [dict(r) for r in rows_all]
    key = f"puuid:{puuid}:queue:{queue or 'any'}"
    metrics = cfg["metrics"]["primary"]

    # windows by count
    for w in cfg["windows"]["counts"]:
        subset = rows[:w]
        subset_rev = list(reversed(subset))
        for m in metrics:
            series = value_of(m, list(reversed(subset)))  # oldest->newest for trend
            val = summarize(value_of(m, subset))
            trend = round(ewma(series), 2) if series else 0.0
            spark = sparkline(series[-8:])
            store.upsert_window(key, m, "count", int(w), float(val), len(subset), float(trend), spark)

    # windows by days
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for d in cfg["windows"]["days"]:
        cutoff = now_ms - d * 24 * 3600 * 1000
        subset = [r for r in rows if r["game_creation_ms"] >= cutoff]
        for m in metrics:
            series = value_of(m, list(reversed(subset)))
            val = summarize(value_of(m, subset))
            trend = round(ewma(series), 2) if series else 0.0
            spark = sparkline(series[-8:])
            store.upsert_window(key, m, "days", int(d), float(val), len(subset), float(trend), spark)

