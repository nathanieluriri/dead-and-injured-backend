# ============================================================================
# MATCH SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:08 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.match import (
    create_match,
    get_match,
    get_matchs,
    update_match,
    delete_match,
)
from schemas.match import MatchCreate, MatchUpdate, MatchOut


async def add_match(match_data: MatchCreate) -> MatchOut:
    """adds an entry of MatchCreate to the database and returns an object

    Returns:
        _type_: MatchOut
    """
    return await create_match(match_data)


async def remove_match(match_id: str):
    """deletes a field from the database and removes MatchCreateobject 

    Raises:
        HTTPException 400: Invalid match ID format
        HTTPException 404:  Match not found
    """
    if not ObjectId.is_valid(match_id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(match_id)}
    result = await delete_match(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Match not found")


async def retrieve_match_by_match_id(id: str) -> MatchOut:
    """Retrieves match object based specific Id 

    Raises:
        HTTPException 404(not found): if  Match not found in the db
        HTTPException 400(bad request): if  Invalid match ID format

    Returns:
        _type_: MatchOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_match(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Match not found")

    return result


async def retrieve_matchs(start=0,stop=100) -> List[MatchOut]:
    """Retrieves MatchOut Objects in a list

    Returns:
        _type_: MatchOut
    """
    return await get_matchs(start=start,stop=stop)


async def update_match_by_id(match_id: str, match_data: MatchUpdate) -> MatchOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Match not found or update failed
        HTTPException 400(not found): Invalid match ID format

    Returns:
        _type_: MatchOut
    """
    if not ObjectId.is_valid(match_id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(match_id)}
    result = await update_match(filter_dict, match_data)

    if not result:
        raise HTTPException(status_code=404, detail="Match not found or update failed")

    return result