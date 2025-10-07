from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "ddragon"
CACHE.mkdir(parents=True, exist_ok=True)

_VERS_CACHE: Dict[str, Any] = {"ver": None, "ts": 0}


def _http() -> httpx.Client:
    return httpx.Client(timeout=10)


def latest_version(force: bool = False) -> str:
    now = time.time()
    if not force and _VERS_CACHE.get("ver") and now - _VERS_CACHE["ts"] < 86400:
        return _VERS_CACHE["ver"]
    with _http() as h:
        r = h.get("https://ddragon.leagueoflegends.com/api/versions.json")
        r.raise_for_status()
        versions = r.json()
    ver = versions[0]
    _VERS_CACHE.update({"ver": ver, "ts": now})
    return ver


def _ver_dir(ver: str) -> Path:
    d = CACHE / ver
    d.mkdir(parents=True, exist_ok=True)
    (d / "img" / "champion").mkdir(parents=True, exist_ok=True)
    (d / "img" / "item").mkdir(parents=True, exist_ok=True)
    (d / "img" / "spell").mkdir(parents=True, exist_ok=True)
    return d


def ensure_ddragon() -> str:
    ver = latest_version()
    d = _ver_dir(ver)
    # fetch JSONs if missing
    assets = {
        "champion.json": f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json",
        "item.json": f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/item.json",
        "summoner.json": f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/summoner.json",
        "runesReforged.json": f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/runesReforged.json",
    }
    with _http() as h:
        for name, url in assets.items():
            p = d / name
            if not p.exists():
                r = h.get(url)
                r.raise_for_status()
                p.write_bytes(r.content)
    return ver


def champ_id_to_name(ver: str, champ_id: int) -> Optional[str]:
    d = _ver_dir(ver)
    p = d / "champion.json"
    if not p.exists():
        ensure_ddragon()
    data = json.loads(p.read_text())
    # map via 'key' -> 'id'
    for name, obj in data.get("data", {}).items():
        try:
            if int(obj.get("key")) == champ_id:
                return obj.get("id")
        except Exception:
            continue
    return None


def spell_id_to_name(ver: str, spell_id: int) -> Optional[str]:
    d = _ver_dir(ver)
    p = d / "summoner.json"
    if not p.exists():
        ensure_ddragon()
    data = json.loads(p.read_text())
    for name, obj in data.get("data", {}).items():
        try:
            if int(obj.get("key")) == spell_id:
                return obj.get("id")
        except Exception:
            continue
    return None


def asset_path_png(kind: str, ver: str, name_or_id: str) -> str:
    if kind == "champion":
        return f"https://ddragon.leagueoflegends.com/cdn/{ver}/img/champion/{name_or_id}.png"
    if kind == "item":
        return f"https://ddragon.leagueoflegends.com/cdn/{ver}/img/item/{name_or_id}.png"
    if kind == "summoner":
        return f"https://ddragon.leagueoflegends.com/cdn/{ver}/img/spell/{name_or_id}.png"
    raise ValueError("unknown kind")


def ensure_icon(kind: str, ver: str, name_or_id: str) -> Path:
    d = _ver_dir(ver)
    if kind == "champion":
        p = d / "img" / "champion" / f"{name_or_id}.png"
    elif kind == "item":
        p = d / "img" / "item" / f"{name_or_id}.png"
    else:
        p = d / "img" / "spell" / f"{name_or_id}.png"
    if p.exists():
        return p
    url = asset_path_png(kind, ver, name_or_id)
    with _http() as h:
        try:
            r = h.get(url)
            r.raise_for_status()
            p.write_bytes(r.content)
        except Exception:
            # write placeholder 1x1 PNG
            import base64
            png_1x1 = base64.b64decode(
                b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
            )
            p.write_bytes(png_1x1)
    return p

