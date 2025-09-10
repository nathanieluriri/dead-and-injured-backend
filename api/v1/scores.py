
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.scores import (
    ScoresCreate,
    ScoresOut,
    ScoresBase,
    ScoresUpdate,
)
from services.scores_service import (
    add_scores,
    remove_scores,
    retrieve_scoress,
    retrieve_scores_by_scores_id,
    update_scores,
)

router = APIRouter(prefix="/scoress", tags=["Scoress"])

@router.get("/", response_model=APIResponse[List[ScoresOut]])
async def list_scoress():
    items = await retrieve_scoress()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[ScoresOut])
async def get_my_scoress(id: str = Query(..., description="scores ID to fetch specific item")):
    items = await retrieve_scores_by_scores_id(id=id)
    return APIResponse(status_code=200, data=items, detail="scoress items fetched")
