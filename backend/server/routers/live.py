from __future__ import annotations

from fastapi import APIRouter

from core.live import LiveClient


router = APIRouter()


@router.get("/status")
def status():
    lc = LiveClient()
    s = lc.status()
    in_game = s.startswith("in_game")
    return {"ok": True, "data": {"status": s, "in_game": in_game}}

