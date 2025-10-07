from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import get_api_key


def _base(region: str) -> str:
    return f"https://{region}.api.riotgames.com"


@dataclass
class RiotClient:
    region: str
    platform: str
    api_key: str

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "RiotClient":
        key = get_api_key()
        if not key:
            raise RuntimeError("No Riot API key found; set RIOT_API_KEY or run auth")
        return cls(region=cfg["riot"]["region"], platform=cfg["riot"]["platform"], api_key=key)

    def _headers(self) -> Dict[str, str]:
        return {"X-Riot-Token": self.api_key}

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        while True:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "2"))
                time.sleep(retry + 1)
                continue
            resp.raise_for_status()
            return resp.json()

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

