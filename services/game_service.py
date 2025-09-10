# ============================================================================
# GAME SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:19 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.game import (
    create_game,
    get_game,
    get_games,
    update_game,
    delete_game,
)
from schemas.game import GameCreate, GameUpdate, GameOut


async def add_game(game_data: GameCreate) -> GameOut:
    """adds an entry of GameCreate to the database and returns an object

    Returns:
        _type_: GameOut
    """
    return await create_game(game_data)


async def remove_game(game_id: str):
    """deletes a field from the database and removes GameCreateobject 

    Raises:
        HTTPException 400: Invalid game ID format
        HTTPException 404:  Game not found
    """
    if not ObjectId.is_valid(game_id):
        raise HTTPException(status_code=400, detail="Invalid game ID format")

    filter_dict = {"_id": ObjectId(game_id)}
    result = await delete_game(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Game not found")


async def retrieve_game_by_game_id(id: str) -> GameOut:
    """Retrieves game object based specific Id 

    Raises:
        HTTPException 404(not found): if  Game not found in the db
        HTTPException 400(bad request): if  Invalid game ID format

    Returns:
        _type_: GameOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid game ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_game(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Game not found")

    return result


async def retrieve_games(start=0,stop=100) -> List[GameOut]:
    """Retrieves GameOut Objects in a list

    Returns:
        _type_: GameOut
    """
    return await get_games(start=start,stop=stop)


async def update_game_by_id(game_id: str, game_data: GameUpdate) -> GameOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Game not found or update failed
        HTTPException 400(not found): Invalid game ID format

    Returns:
        _type_: GameOut
    """
    if not ObjectId.is_valid(game_id):
        raise HTTPException(status_code=400, detail="Invalid game ID format")

    filter_dict = {"_id": ObjectId(game_id)}
    result = await update_game(filter_dict, game_data)

    if not result:
        raise HTTPException(status_code=404, detail="Game not found or update failed")

    return result