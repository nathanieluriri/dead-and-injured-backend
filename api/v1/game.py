
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.game import (
    GameCreate,
    GameOut,
    GameBase,
    GameUpdate,
)
from services.game_service import (
    add_game,
    remove_game,
    retrieve_games,
    retrieve_game_by_game_id,
    update_game,
)

router = APIRouter(prefix="/games", tags=["Games"])

@router.get("/", response_model=APIResponse[List[GameOut]])
async def list_games():
    items = await retrieve_games()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[GameOut])
async def get_my_games(id: str = Query(..., description="game ID to fetch specific item")):
    items = await retrieve_game_by_game_id(id=id)
    return APIResponse(status_code=200, data=items, detail="games items fetched")
