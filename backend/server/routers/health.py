from __future__ import annotations

from fastapi import APIRouter
import time
import sqlite3

from core.live import LiveClient
from core.riot import RiotClient
from core.store import Store
from ..deps import config as get_cfg
from ..ingest.ddragon import ensure_ddragon, latest_version


router = APIRouter()

_RIOT_HEALTH = {"status": "down", "ts": 0}


@router.get("/health")
def health():
    t0 = time.time()
    # DB
    store = Store()
    schema_version = 3
    try:
        with store.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version','3')")
            con.commit()
            row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            schema_version = int(row[0]) if row else 3
        db_resp = {"ok": True, "schema_version": schema_version}
    except Exception:
        db_resp = {"ok": False, "schema_version": schema_version}

    # Riot API health (cached ≥60s)
    cfg = get_cfg()
    now = time.time()
    status = _RIOT_HEALTH["status"] if now - _RIOT_HEALTH["ts"] < 60 else None
    if status is None:
        try:
            RiotClient.from_config(cfg)
            status = "ok"
        except Exception:
            status = "down"
        _RIOT_HEALTH.update({"status": status, "ts": now})
    riot_resp = {"status": status, "last_check_epoch": int(_RIOT_HEALTH["ts"]) }

    # Live client
    live_status = "down"
    last_err = None
    try:
        lc = LiveClient()
        s = lc.status()
        live_status = "up" if s in ("no_game",) or s.startswith("in_game") else "down"
    except Exception as e:
        last_err = str(e)
        live_status = "down"

    # DDragon
    try:
        ver = latest_version()
        assets_cached = ( (Store.__module__) is not None)  # dummy to avoid flake
        # quick: check champion.json exists
        from ..ingest.ddragon import _ver_dir
        d = _ver_dir(ver)
        assets_cached = (d / "champion.json").exists()
        ddragon = {"version": ver, "assets_cached": assets_cached}
    except Exception:
        ddragon = {"version": "unknown", "assets_cached": False}

    data = {
        "version": "1.1.0",
        "db": db_resp,
        "riot_api": riot_resp,
        "live_client": {"status": live_status, "last_error": last_err},
        "ddragon": ddragon,
    }
    return {"ok": True, "data": data}
