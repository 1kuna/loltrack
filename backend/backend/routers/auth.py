from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..deps import get_config, save_config, set_api_key
from loltrack.riot import RiotClient


router = APIRouter()
config_router = APIRouter()


@router.post("/riot-key")
def set_riot_key(payload: Dict[str, str]):
    key = payload.get("key")
    if not key:
        return {"ok": False, "error": {"code": "INVALID_INPUT", "message": "Riot API key required"}}
    # Save first so RiotClient can read from keyring
    set_api_key(key)
    # Validate key against Riot status endpoint
    try:
        cfg = get_config()
        rc = RiotClient.from_config(cfg)
        is_valid = rc.verify_key()
        if not is_valid:
            return {"ok": False, "error": {"code": "INVALID_INPUT", "message": "Invalid or expired Riot API key"}}
    except Exception as e:
        # Treat network failures as upstream issue
        return {"ok": False, "error": {"code": "RIOT_DOWN", "message": "Could not reach Riot API. Try again later."}}
    return {"ok": True, "data": {"verified": True}}


@router.post("/riot-id")
def set_riot_id(payload: Dict[str, str]):
    riot_id = payload.get("riot_id")
    if not riot_id or "#" not in riot_id:
        return {"ok": False, "error": {"code": "INVALID_INPUT", "message": "Use GameName#TAG"}}
    cfg = get_config()
    # Pre-req: API key must be present/valid
    try:
        rc = RiotClient.from_config(cfg)
        if not rc.verify_key():
            return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add a valid Riot API key first."}}
    except Exception:
        return {"ok": False, "error": {"code": "MISSING_PREREQ", "message": "Add a valid Riot API key first."}}
    cfg.setdefault("player", {})["riot_id"] = riot_id
    game, tag = riot_id.split("#", 1)
    rc = RiotClient.from_config(cfg)
    acct = rc.resolve_account(game, tag)
    cfg["player"]["puuid"] = acct.get("puuid")
    save_config(cfg)
    return {"ok": True, "data": {"puuid": acct.get("puuid"), "region": cfg["riot"]["region"], "platform": cfg["riot"]["platform"]}}


@config_router.get("/config")
def get_cfg():
    return {"ok": True, "data": get_config()}


@config_router.put("/config")
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
