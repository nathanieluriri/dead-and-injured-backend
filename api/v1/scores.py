from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from schemas.response_schema import APIResponse, ok_response
from schemas.scores import ScoresOut
from schemas.tokens_schema import accessTokenOut
from security.auth import verify_token
from services.scores_service import retrieve_score_stats_for_user, retrieve_scoress

router = APIRouter(prefix="/scores", tags=["Scores"], dependencies=[Depends(verify_token)])
legacy_router = APIRouter(prefix="/scoress", tags=["Scoress"], dependencies=[Depends(verify_token)], include_in_schema=False)


@router.get("/", response_model=APIResponse[List[ScoresOut]])
@legacy_router.get("/", response_model=APIResponse[List[ScoresOut]])
async def list_scores() -> APIResponse[List[ScoresOut]]:
    items = await retrieve_scoress()
    return ok_response(data=items, message="Scores fetched successfully")


@router.get("/me/stats", response_model=APIResponse[dict[str, float | int]])
@legacy_router.get("/me/stats", response_model=APIResponse[dict[str, float | int]])
async def get_my_score_stats(token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, float | int]]:
    stats = await retrieve_score_stats_for_user(token.userId)
    return ok_response(data=stats, message="Score stats fetched successfully")


router.include_router(legacy_router)
