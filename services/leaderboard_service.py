# ============================================================================
# LEADERBOARD SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:29 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.leaderboard import (
    create_leaderboard,
    get_leaderboard,
    get_leaderboards,
    update_leaderboard,
    delete_leaderboard,
)
from schemas.leaderboard import LeaderboardCreate, LeaderboardUpdate, LeaderboardOut


async def add_leaderboard(leaderboard_data: LeaderboardCreate) -> LeaderboardOut:
    """adds an entry of LeaderboardCreate to the database and returns an object

    Returns:
        _type_: LeaderboardOut
    """
    return await create_leaderboard(leaderboard_data)


async def remove_leaderboard(leaderboard_id: str):
    """deletes a field from the database and removes LeaderboardCreateobject 

    Raises:
        HTTPException 400: Invalid leaderboard ID format
        HTTPException 404:  Leaderboard not found
    """
    if not ObjectId.is_valid(leaderboard_id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(leaderboard_id)}
    result = await delete_leaderboard(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Leaderboard not found")


async def retrieve_leaderboard_by_leaderboard_id(id: str) -> LeaderboardOut:
    """Retrieves leaderboard object based specific Id 

    Raises:
        HTTPException 404(not found): if  Leaderboard not found in the db
        HTTPException 400(bad request): if  Invalid leaderboard ID format

    Returns:
        _type_: LeaderboardOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_leaderboard(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Leaderboard not found")

    return result


async def retrieve_leaderboards(start=0,stop=100) -> List[LeaderboardOut]:
    """Retrieves LeaderboardOut Objects in a list

    Returns:
        _type_: LeaderboardOut
    """
    return await get_leaderboards(start=start,stop=stop)


async def update_leaderboard_by_id(leaderboard_id: str, leaderboard_data: LeaderboardUpdate) -> LeaderboardOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Leaderboard not found or update failed
        HTTPException 400(not found): Invalid leaderboard ID format

    Returns:
        _type_: LeaderboardOut
    """
    if not ObjectId.is_valid(leaderboard_id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(leaderboard_id)}
    result = await update_leaderboard(filter_dict, leaderboard_data)

    if not result:
        raise HTTPException(status_code=404, detail="Leaderboard not found or update failed")

    return result