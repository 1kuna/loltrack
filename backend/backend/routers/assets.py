from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..ingest.ddragon import ensure_ddragon, champ_id_to_name, spell_id_to_name, ensure_icon


router = APIRouter()


@router.get("/assets/champion/{champ_id}.png")
def champion_icon(champ_id: int):
    ver = ensure_ddragon()
    name = champ_id_to_name(ver, champ_id) or "Unknown"
    p = ensure_icon("champion", ver, name)
    return FileResponse(str(p))


@router.get("/assets/item/{item_id}.png")
def item_icon(item_id: int):
    ver = ensure_ddragon()
    p = ensure_icon("item", ver, str(item_id))
    return FileResponse(str(p))


@router.get("/assets/summoner/{spell_id}.png")
def summoner_icon(spell_id: int):
    ver = ensure_ddragon()
    name = spell_id_to_name(ver, spell_id) or "SummonerFlash"
    p = ensure_icon("summoner", ver, name)
    return FileResponse(str(p))

