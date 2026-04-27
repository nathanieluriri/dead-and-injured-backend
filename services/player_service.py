# ============================================================================
# PLAYER SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:12 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.player import (
    create_player,
    get_player,
    get_player_by_user_and_game,
    get_players,
    update_player,
    delete_player,
)
from schemas.player import PlayerCreate, PlayerUpdate, PlayerOut


async def add_player(player_data: PlayerCreate) -> PlayerOut:
    """adds an entry of PlayerCreate to the database and returns an object

    Returns:
        _type_: PlayerOut
    """
    return await create_player(player_data)


async def remove_player(player_id: str):
    """deletes a field from the database and removes PlayerCreateobject 

    Raises:
        HTTPException 400: Invalid player ID format
        HTTPException 404:  Player not found
    """
    if not ObjectId.is_valid(player_id):
        raise HTTPException(status_code=400, detail="Invalid player ID format")

    filter_dict = {"_id": ObjectId(player_id)}
    result = await delete_player(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Player not found")


async def retrieve_player_by_player_id(id: str) -> PlayerOut:
    """Retrieves player object based specific Id 

    Raises:
        HTTPException 404(not found): if  Player not found in the db
        HTTPException 400(bad request): if  Invalid player ID format

    Returns:
        _type_: PlayerOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid player ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_player(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Player not found")

    return result


async def retrieve_players(start=0,stop=100) -> List[PlayerOut]:
    """Retrieves PlayerOut Objects in a list

    Returns:
        _type_: PlayerOut
    """
    return await get_players(start=start,stop=stop)


async def update_player_by_id(player_id: str, player_data: PlayerUpdate) -> PlayerOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Player not found or update failed
        HTTPException 400(not found): Invalid player ID format

    Returns:
        _type_: PlayerOut
    """
    if not ObjectId.is_valid(player_id):
        raise HTTPException(status_code=400, detail="Invalid player ID format")

    filter_dict = {"_id": ObjectId(player_id)}
    result = await update_player(filter_dict, player_data)

    if not result:
        raise HTTPException(status_code=404, detail="Player not found or update failed")

    return result


async def retrieve_player_for_user_in_game(user_id: str, game_id: str) -> PlayerOut | None:
    return await get_player_by_user_and_game(user_id=user_id, game_id=game_id)
