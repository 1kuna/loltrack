from __future__ import annotations

from typing import Any, Dict

from core.config import get_config, save_config, get_api_key, set_api_key
from core.store import Store
from core.riot import RiotClient


def config() -> Dict[str, Any]:
    return get_config()


def store() -> Store:
    return Store()


def riot() -> RiotClient:
    return RiotClient.from_config(get_config())


__all__ = [
    "config",
    "store",
    "riot",
    "get_config",
    "save_config",
    "get_api_key",
    "set_api_key",
]
