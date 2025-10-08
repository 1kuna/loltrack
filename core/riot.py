from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import threading
from collections import deque

import requests

from .config import get_api_key


def _base(region: str) -> str:
    return f"https://{region}.api.riotgames.com"


@dataclass
class RiotClient:
    region: str
    platform: str
    api_key: str
    kind: str = "fg"  # 'fg' (interactive), 'bg' (background)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any], kind: str = "fg") -> "RiotClient":
        key = get_api_key()
        if not key:
            raise RuntimeError("No Riot API key found; set RIOT_API_KEY or run auth")
        return cls(region=cfg["riot"]["region"], platform=cfg["riot"]["platform"], api_key=key, kind=kind)

    def _headers(self) -> Dict[str, str]:
        return {"X-Riot-Token": self.api_key}

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        while True:
            _RATE_LIMITER.acquire(self.kind)
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 429:
                # Respect Retry-After and also let limiter naturally pace subsequent calls
                retry = int(resp.headers.get("Retry-After", "2"))
                time.sleep(retry + 1)
                continue
            resp.raise_for_status()
            return resp.json()

    def verify_key(self) -> bool:
        """Best-effort verification of API key via a low-cost status endpoint.

        Returns True if the key appears valid (2xx), False on 401/403.
        Raises on network errors other than auth/rate limits.
        """
        url = f"{_base(self.platform)}/lol/status/v4/platform-data"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code in (401, 403):
                return False
            if resp.status_code == 429:
                # Treat rate limit as valid key
                return True
            resp.raise_for_status()
            return True
        except requests.RequestException:
            # Network or other error; bubble up to caller for mapping
            raise

    # Account V1
    def resolve_account(self, game_name: str, tag_line: str) -> Dict[str, Any]:
        url = f"{_base(self.region)}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return self._get(url)

    # Match V5
    def match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20, start_time: Optional[int] = None) -> List[str]:
        url = f"{_base(self.region)}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: Dict[str, Any] = {"start": start, "count": count}
        if start_time is not None:
            params["startTime"] = start_time
        return self._get(url, params=params)

    def get_match(self, match_id: str) -> Dict[str, Any]:
        url = f"{_base(self.region)}/lol/match/v5/matches/{match_id}"
        return self._get(url)

    def get_timeline(self, match_id: str) -> Dict[str, Any]:
        url = f"{_base(self.region)}/lol/match/v5/matches/{match_id}/timeline"
        return self._get(url)

    # Champion Mastery V4
    def champion_masteries_by_puuid(self, puuid: str) -> List[Dict[str, Any]]:
        url = f"{_base(self.platform)}/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
        return self._get(url)


class _RateLimiter:
    """Global token-gate for Riot requests.

    Enforces both 20 req / 1s and 100 req / 120s across the process.
    Background ('bg') calls respect a soft reserve for foreground ('fg') calls.
    """

    def __init__(self, per_sec: int = 20, per_120s: int = 100, fg_reserve_sec: int = 8, fg_reserve_120s: int = 40) -> None:
        self.per_sec = per_sec
        self.per_120s = per_120s
        self.fg_reserve_sec = fg_reserve_sec
        self.fg_reserve_120s = fg_reserve_120s
        self._q1 = deque()  # timestamps (monotonic) for 1s window
        self._q2 = deque()  # timestamps for 120s window
        self._lock = threading.Lock()

    def acquire(self, kind: str) -> None:
        # Busy-wait with short sleeps to maintain pacing; background yields more.
        while True:
            wait = self._try_acquire(kind)
            if wait <= 0:
                return
            time.sleep(min(wait, 0.05 if kind == "fg" else 0.2))

    def _try_acquire(self, kind: str) -> float:
        now = time.monotonic()
        with self._lock:
            # prune
            while self._q1 and now - self._q1[0] > 1.0:
                self._q1.popleft()
            while self._q2 and now - self._q2[0] > 120.0:
                self._q2.popleft()
            n1 = len(self._q1)
            n2 = len(self._q2)
            # global caps
            if n1 >= self.per_sec or n2 >= self.per_120s:
                # compute next availability
                t1 = (1.0 - (now - self._q1[0])) if self._q1 else 0.05
                t2 = (120.0 - (now - self._q2[0])) if self._q2 else 0.05
                return max(min(t1, t2), 0.01)
            # background reserve check
            if kind == "bg":
                if n1 >= (self.per_sec - self.fg_reserve_sec) or n2 >= (self.per_120s - self.fg_reserve_120s):
                    # hint sleep until some tokens free
                    t1 = (1.0 - (now - self._q1[0])) if self._q1 else 0.05
                    t2 = (120.0 - (now - self._q2[0])) if self._q2 else 0.05
                    return max(min(t1, t2), 0.05)
            # take token
            self._q1.append(now)
            self._q2.append(now)
            return 0.0


_RATE_LIMITER = _RateLimiter()
