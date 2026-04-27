from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from schemas.response_schema import APIResponse, ok_response
from schemas.secret import SecretOut
from schemas.tokens_schema import accessTokenOut
from security.auth import verify_token
from services.player_service import retrieve_players
from services.secret_service import retrieve_secret_for_player

router = APIRouter(prefix="/secrets", tags=["Secrets"], dependencies=[Depends(verify_token)])


@router.get("/me", response_model=APIResponse[List[SecretOut]])
async def get_my_secrets(token: accessTokenOut = Depends(verify_token)) -> APIResponse[List[SecretOut]]:
    players = [player for player in await retrieve_players() if player.user_id == token.userId]
    secrets: list[SecretOut] = []
    for player in players:
        secret = await retrieve_secret_for_player(player.id)
        if secret is not None:
            secrets.append(secret)
    if not secrets:
        raise HTTPException(status_code=404, detail="No secrets found for user")
    return ok_response(data=secrets, message="Secrets fetched successfully")
