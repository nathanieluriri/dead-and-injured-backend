from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from schemas.player import PlayerOut
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from security.auth import verify_token
from services.player_service import retrieve_player_by_player_id, retrieve_players

router = APIRouter(prefix="/players", tags=["Players"], dependencies=[Depends(verify_token)])


@router.get("/", response_model=APIResponse[List[PlayerOut]])
async def list_players() -> APIResponse[List[PlayerOut]]:
    items = await retrieve_players()
    return ok_response(data=items, message="Players fetched successfully")


@router.get("/me", response_model=APIResponse[List[PlayerOut]])
async def get_my_players(token: accessTokenOut = Depends(verify_token)) -> APIResponse[List[PlayerOut]]:
    players = [player for player in await retrieve_players() if player.user_id == token.userId]
    if not players:
        raise HTTPException(status_code=404, detail="No players found for user")
    return ok_response(data=players, message="Player records fetched successfully")
