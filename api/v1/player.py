
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.player import (
    PlayerCreate,
    PlayerOut,
    PlayerBase,
    PlayerUpdate,
)
from services.player_service import (
    add_player,
    remove_player,
    retrieve_players,
    retrieve_player_by_player_id,
    update_player,
)

router = APIRouter(prefix="/players", tags=["Players"])

@router.get("/", response_model=APIResponse[List[PlayerOut]])
async def list_players():
    items = await retrieve_players()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[PlayerOut])
async def get_my_players(id: str = Query(..., description="player ID to fetch specific item")):
    items = await retrieve_player_by_player_id(id=id)
    return APIResponse(status_code=200, data=items, detail="players items fetched")
