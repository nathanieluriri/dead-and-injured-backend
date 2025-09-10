
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.leaderboard import (
    LeaderboardCreate,
    LeaderboardOut,
    LeaderboardBase,
    LeaderboardUpdate,
)
from services.leaderboard_service import (
    add_leaderboard,
    remove_leaderboard,
    retrieve_leaderboards,
    retrieve_leaderboard_by_leaderboard_id,
    update_leaderboard,
)

router = APIRouter(prefix="/leaderboards", tags=["Leaderboards"])

@router.get("/", response_model=APIResponse[List[LeaderboardOut]])
async def list_leaderboards():
    items = await retrieve_leaderboards()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[LeaderboardOut])
async def get_my_leaderboards(id: str = Query(..., description="leaderboard ID to fetch specific item")):
    items = await retrieve_leaderboard_by_leaderboard_id(id=id)
    return APIResponse(status_code=200, data=items, detail="leaderboards items fetched")
