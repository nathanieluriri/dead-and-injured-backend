
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.match import (
    MatchCreate,
    MatchOut,
    MatchBase,
    MatchUpdate,
)
from services.match_service import (
    add_match,
    remove_match,
    retrieve_matchs,
    retrieve_match_by_match_id,
    update_match,
)

router = APIRouter(prefix="/matchs", tags=["Matchs"])

@router.get("/", response_model=APIResponse[List[MatchOut]])
async def list_matchs():
    items = await retrieve_matchs()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[MatchOut])
async def get_my_matchs(id: str = Query(..., description="match ID to fetch specific item")):
    items = await retrieve_match_by_match_id(id=id)
    return APIResponse(status_code=200, data=items, detail="matchs items fetched")
