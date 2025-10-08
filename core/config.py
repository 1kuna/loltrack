from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import keyring
import yaml


APP_DIR_NAME = "loltrack"
CONFIG_FILE_NAME = "config.yaml"
DB_FILE_NAME = "loltrack.db"
KEYRING_SERVICE = "loltrack.riot"


DEFAULT_CONFIG: Dict[str, Any] = {
    "riot": {
        "api_key_env": "RIOT_API_KEY",
        "region": "americas",  # routing for Match-V5
        "platform": "na1",  # platform for account/summoner
    },
    "player": {
        "riot_id": "",
        "puuid": "",
        "track_queues": [420],
    },
    "windows": {
        "counts": [5, 10, 20],
        "days": [30, 60],
    },
    "render": {
        "theme": "dark",
        "palette": {"ok": "green", "warn": "yellow", "bad": "red", "accent": "cyan", "neutral": "grey70"},
    },
    "metrics": {
        "primary": [
            "DL14",
            "CS10",
            "CS14",
            "GD10",
            "XPD10",
            "FirstRecall",
            "CtrlWardsPre14",
            "KPEarly",
        ],
        "targets": {
            "CS10": {"mode": "auto", "manual_floor": 60},
            "DL14": {"mode": "auto"},
            "GD10": {"mode": "auto"},
        },
        "weights": {
            "DL14": 1.2,
            "CS10": 1.0,
            "CS14": 0.8,
            "GD10": 1.0,
            "XPD10": 1.0,
            "KPEarly": 0.6,
            "CtrlWardsPre14": 0.6,
            "FirstRecall": 0.4,
        },
    },
    "gis": {
        "minMatchesForGIS": 5,
        "minMatchesForFocus": 8,
        "minPrimaryGap": -4.0,
        "minPrimaryLead": 2.0,
        "hysteresisMatches": 3,
        "maxBandForFocus": 6.0,
        "secondaryGap": -2.0,
        "rankedQueues": [420, 440],
        "maxNegativeImpactLowMastery": 3.0,
        # Floor for standardization sigma to avoid z=0 collapse early on
        "epsSigma": 0.5,
    },
    # Goals configuration (targets + ratchet)
    "goals": {
        "conservative_floor": {
            "CS10": 55,
            "GD10": -200
        },
        "step_min": {
            "CS10": 3,
            "GD10": 50
        },
        "ratchet_inc": {
            "CS10": 3,
            "GD10": 50
        }
    },
}


def _user_config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    # Linux and others
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def _user_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        localappdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if localappdata:
            return Path(localappdata) / APP_DIR_NAME
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def config_path() -> str:
    return str(_user_config_dir() / CONFIG_FILE_NAME)


def db_path() -> str:
    return str(_user_data_dir() / DB_FILE_NAME)


def ensure_paths() -> None:
    _user_config_dir().mkdir(parents=True, exist_ok=True)
    _user_data_dir().mkdir(parents=True, exist_ok=True)
    cfg_file = Path(config_path())
    if not cfg_file.exists():
        cfg_file.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False))


def get_config() -> Dict[str, Any]:
    ensure_paths()
    with open(config_path(), "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # merge defaults shallowly
    def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(a)
        for k, v in b.items():
            if isinstance(v, dict):
                out[k] = merge(out.get(k, {}), v)
            else:
                out.setdefault(k, v)
        return out

    return merge(cfg, DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_paths()
    with open(config_path(), "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def open_config_in_editor() -> bool:
    path = config_path()
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return True
    except Exception:
        return False


def get_api_key() -> str | None:
    # prefer keyring
    key = keyring.get_password(KEYRING_SERVICE, "api_key")
    if key:
        return key
    # fallback env
    cfg = get_config()
    env_name = cfg.get("riot", {}).get("api_key_env", "RIOT_API_KEY")
    return os.getenv(env_name)


def set_api_key(value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, "api_key", value)
