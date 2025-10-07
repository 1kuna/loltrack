from __future__ import annotations

import time
from typing import Any, Dict, Generator

from loltrack.live import LiveClient
from loltrack.config import get_config


def stream_live_payloads(live: LiveClient | None = None) -> Generator[Dict[str, Any], None, None]:
    lc = live or LiveClient()
    last_t = None
    while True:
        try:
            data = lc.allgamedata()
        except Exception:
            yield {"event": "waiting"}
            time.sleep(1)
            continue

        gd = data.get("gameData", {})
        t = gd.get("gameTime", 0.0)
        scores = data.get("activePlayer", {}).get("scores", {})
        cs_now = int(scores.get("creepScore") or 0)
        deaths = int(scores.get("deaths") or 0)
        csmin = cs_now / max(t / 60.0, 1e-6)

        cfg = get_config()
        floor = int((cfg.get("metrics",{}).get("targets",{}).get("CS10",{}) or {}).get("manual_floor", 60))
        proj10 = int(csmin * 10)
        if proj10 >= floor + 3:
            pace = "ahead"
        elif proj10 >= floor:
            pace = "on_pace"
        else:
            pace = "behind"

        payload = {
            "t": int(time.time()),
            "gameTime": t,
            "early": {
                "dl14_on_track": bool(deaths == 0 and t < 14 * 60),
                "cs": cs_now,
                "cs10_eta": pace,
                "gold10_est": None,
                "gd10_est": None,
                "xp10_est": None,
                "xpd10_est": None,
                "ctrlw_pre14_progress": {"have": None, "need": 1},
                "recall_window": {"in_window": None, "range": "3:15–4:00"},
                "tip": "Buy 1 control ward before 10:00",
            },
        }
        yield payload
        time.sleep(1)
        if last_t is not None and t <= last_t:
            yield {"event": "game_end"}
            return
        last_t = t
