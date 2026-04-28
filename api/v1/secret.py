from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request

from core.rate_limit import limiter
from schemas.response_schema import APIResponse, ok_response
from schemas.secret import SecretOut
from schemas.tokens_schema import accessTokenOut
from security.auth import verify_token
from services.player_service import retrieve_players
from services.secret_service import retrieve_secret_for_player

router = APIRouter(prefix="/secrets", tags=["Secrets"], dependencies=[Depends(verify_token)])


@router.get("/me", response_model=APIResponse[List[SecretOut]])
@limiter.limit("60/minute")
async def get_my_secrets(
    request: Request,
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[List[SecretOut]]:
    players = [player for player in await retrieve_players() if player.user_id == token.userId]
    secrets: list[SecretOut] = []
    for player in players:
        secret = await retrieve_secret_for_player(player.id)
        if secret is not None:
            secrets.append(secret)
    return ok_response(data=secrets, message="Secrets fetched successfully")
