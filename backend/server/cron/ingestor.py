from __future__ import annotations

import threading
import time

from core.store import Store
from core.metrics import ingest_and_compute_recent
from core.riot import RiotClient
from ..deps import config as get_cfg
from core.live import LiveClient
from core.windows import rebuild_windows


_STARTED = False
_INTERVAL_SEC = 300  # 5 minutes


def start_ingestor() -> None:
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    th = threading.Thread(target=_loop, daemon=True)
    th.start()


def _loop():
    # initial backoff
    time.sleep(20)
    while True:
        try:
            _tick()
        except Exception:
            pass
        time.sleep(_INTERVAL_SEC)


def _tick():
    # Skip while in live game
    try:
        if LiveClient().status().startswith("in_game"):
            return
    except Exception:
        pass
    cfg = get_cfg()
    puuid = (cfg.get("player", {}) or {}).get("puuid")
    if not puuid:
        return
    store = Store()
    try:
        rc = RiotClient.from_config(cfg, kind="bg")
    except Exception:
        return
    # Ingest a tiny slice to catch fresh matches
    n = ingest_and_compute_recent(rc, store, puuid, since="2h", count=5, queue_filter=None)
    if n > 0:
        try:
            rebuild_windows(store, cfg)
        except Exception:
            pass

