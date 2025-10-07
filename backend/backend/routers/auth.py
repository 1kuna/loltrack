from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..deps import get_config, save_config, set_api_key
from loltrack.riot import RiotClient


router = APIRouter()


@router.post("/riot-key")
def set_riot_key(payload: Dict[str, str]):
    key = payload.get("key")
    if not key:
        return {"ok": False, "error": {"code": "missing_key", "message": "key required"}}
    set_api_key(key)
    return {"ok": True}


@router.post("/riot-id")
def set_riot_id(payload: Dict[str, str]):
    riot_id = payload.get("riot_id")
    if not riot_id or "#" not in riot_id:
        return {"ok": False, "error": {"code": "bad_riot_id", "message": "Use GameName#TAG"}}
    cfg = get_config()
    cfg.setdefault("player", {})["riot_id"] = riot_id

    rc = RiotClient.from_config(cfg)
    game, tag = riot_id.split("#", 1)
    acct = rc.resolve_account(game, tag)
    cfg["player"]["puuid"] = acct.get("puuid")
    save_config(cfg)
    return {"ok": True, "data": {"puuid": acct.get("puuid"), "region": cfg["riot"]["region"], "platform": cfg["riot"]["platform"]}}


@router.get("/config")
def get_cfg():
    return {"ok": True, "data": get_config()}


@router.put("/config")
def put_cfg(payload: Dict[str, Any]):
    cfg = get_config()
    # shallow merge
    for k, v in payload.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    save_config(cfg)
    return {"ok": True, "data": cfg}
