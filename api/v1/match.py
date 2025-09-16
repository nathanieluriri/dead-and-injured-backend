
from fastapi import APIRouter, HTTPException, Query, status, Path,Depends
from typing import List
from schemas.response_schema import APIResponse
from schemas.match import (
    MatchCreate,
    MatchOut,
    MatchBase,
    MatchUpdate,
)
from schemas.tokens_schema import accessTokenOut
from services.match_service import (
    add_match,
    remove_match,
    retrieve_matchs,
    retrieve_match_by_match_id,
    update_match,
)
from security.auth import verify_token

router = APIRouter(prefix="/matchs",dependencies=[Depends(verify_token)], tags=["Matchs"])

@router.get("/{gameId}/{start}/{stop}", response_model=APIResponse[List[MatchOut]])
async def list_matchs(gameId:str,start:int=0,stop:int=100,token:accessTokenOut = Depends(verify_token)):
    items = await retrieve_matchs(gameId,start,stop)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[MatchOut])
async def get_my_matchs(id: str = Query(..., description="match ID to fetch specific item")):
    items = await retrieve_match_by_match_id(id=id)
    return APIResponse(status_code=200, data=items, detail="matchs items fetched")


@router.post("/multiplayer-round", response_model=APIResponse[MatchOut])
async def play_match(match_data:MatchBase,token:accessTokenOut = Depends(verify_token)):
    
    items = await add_match(match_data)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")