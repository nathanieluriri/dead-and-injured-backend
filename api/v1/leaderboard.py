from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query, Request

from core.rate_limit import limiter
from schemas.leaderboard import LeaderboardOut
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from security.auth import verify_token
from services.leaderboard_service import rebuild_leaderboard, retrieve_global_leaderboard, retrieve_my_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["Leaderboards"], dependencies=[Depends(verify_token)])
legacy_router = APIRouter(prefix="/leaderboards", tags=["Leaderboards"], dependencies=[Depends(verify_token)], include_in_schema=False)


@router.get("/global", response_model=APIResponse[List[LeaderboardOut]])
@legacy_router.get("/global", response_model=APIResponse[List[LeaderboardOut]])
@limiter.limit("60/minute")
async def list_global_leaderboard(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> APIResponse[List[LeaderboardOut]]:
    items = await retrieve_global_leaderboard(limit=limit, offset=offset)
    if not items:
        await rebuild_leaderboard()
        items = await retrieve_global_leaderboard(limit=limit, offset=offset)
    return ok_response(data=items, message="Leaderboard fetched successfully")


@router.get("/me", response_model=APIResponse[LeaderboardOut])
@legacy_router.get("/me", response_model=APIResponse[LeaderboardOut])
async def get_my_leaderboard(token: accessTokenOut = Depends(verify_token)) -> APIResponse[LeaderboardOut]:
    item = await retrieve_my_leaderboard(token.userId)
    return ok_response(data=item, message="Leaderboard entry fetched successfully")


router.include_router(legacy_router)
