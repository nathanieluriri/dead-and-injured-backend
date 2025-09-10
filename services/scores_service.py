# ============================================================================
# SCORES SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:23 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.scores import (
    create_scores,
    get_scores,
    get_scoress,
    update_scores,
    delete_scores,
)
from schemas.scores import ScoresCreate, ScoresUpdate, ScoresOut


async def add_scores(scores_data: ScoresCreate) -> ScoresOut:
    """adds an entry of ScoresCreate to the database and returns an object

    Returns:
        _type_: ScoresOut
    """
    return await create_scores(scores_data)


async def remove_scores(scores_id: str):
    """deletes a field from the database and removes ScoresCreateobject 

    Raises:
        HTTPException 400: Invalid scores ID format
        HTTPException 404:  Scores not found
    """
    if not ObjectId.is_valid(scores_id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(scores_id)}
    result = await delete_scores(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scores not found")


async def retrieve_scores_by_scores_id(id: str) -> ScoresOut:
    """Retrieves scores object based specific Id 

    Raises:
        HTTPException 404(not found): if  Scores not found in the db
        HTTPException 400(bad request): if  Invalid scores ID format

    Returns:
        _type_: ScoresOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_scores(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Scores not found")

    return result


async def retrieve_scoress(start=0,stop=100) -> List[ScoresOut]:
    """Retrieves ScoresOut Objects in a list

    Returns:
        _type_: ScoresOut
    """
    return await get_scoress(start=start,stop=stop)


async def update_scores_by_id(scores_id: str, scores_data: ScoresUpdate) -> ScoresOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Scores not found or update failed
        HTTPException 400(not found): Invalid scores ID format

    Returns:
        _type_: ScoresOut
    """
    if not ObjectId.is_valid(scores_id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(scores_id)}
    result = await update_scores(filter_dict, scores_data)

    if not result:
        raise HTTPException(status_code=404, detail="Scores not found or update failed")

    return result