from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..deps import get_config, save_config, set_api_key
from core.riot import RiotClient


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
    # Validate metric target overrides: rate metrics must be fractions 0..1
    try:
        incoming_targets = ((payload.get("metrics") or {}).get("targets") or {})
        # HUMAN_META duplicated here would be messy; import lazily
        from .metrics import HUMAN_META as _HUMAN_META  # type: ignore
        for m, ent in (incoming_targets or {}).items():
            if not isinstance(ent, dict):
                continue
            unit = (_HUMAN_META.get(m, {}) or {}).get("unit")
            if unit == "rate":
                val = ent.get("manual_floor")
                if val is None:
                    continue
                try:
                    f = float(val)
                except Exception:
                    raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": f"{m} must be 0–100% (e.g., 65 or 0.65)"})
                # Accept canonical fraction only; frontend normalizes already
                if f < 0 or f > 1:
                    raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": f"{m} must be 0–100% (e.g., 65 or 0.65)"})
    except HTTPException:
        raise
    except Exception:
        # Do not block other config updates if validation probing fails
        pass
    # shallow merge
    for k, v in payload.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    save_config(cfg)
    return {"ok": True, "data": cfg}
