from __future__ import annotations

import requests


BASE = "https://127.0.0.1:2999/liveclientdata"


class LiveClient:
    def __init__(self) -> None:
        self.session = requests.Session()

    def _get(self, path: str):
        url = f"{BASE}/{path.lstrip('/')}"
        resp = self.session.get(url, timeout=3, verify=False)  # local self-signed
        resp.raise_for_status()
        return resp.json()

    def allgamedata(self):
        return self._get("allgamedata")

    def activeplayer(self):
        return self._get("activeplayer")

    def playerlist(self):
        return self._get("playerlist")

    def eventdata(self):
        return self._get("eventdata")

    def status(self) -> str:
        try:
            data = self.allgamedata()
            t = data.get("gameData", {}).get("gameTime")
            if t is not None:
                return f"in_game t={t:.1f}s"
        except Exception:
            pass
        return "no_game"

