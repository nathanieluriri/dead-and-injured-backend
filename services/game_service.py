# ============================================================================
# GAME SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:59:19 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

import time
from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.game import (
    create_game,
    get_game,
    get_expirable_games,
    get_games,
    mark_games_expired,
    update_game,
    delete_game,
)
from schemas.game import GameCreate, GameUpdate, GameOut,GameStatus,GameSettings,GameType
from services.presence_service import reset_for_game_participants


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

    return await expire_game_if_needed(result)


async def retrieve_games(start=0,stop=100) -> List[GameOut]:
    """Retrieves GameOut Objects in a list

    Returns:
        _type_: GameOut
    """
    return await get_games(start=start,stop=stop)

async def retrieve_available_games(start=0,stop=100) -> List[GameOut]:
    """Retrieves GameOut Objects in a list

    Returns:
        _type_: GameOut
    """
    flter ={
    'settings.game_type': 'Multiplayer', 
    'settings.is_public': True, 
    'status': 'waiting'
        }
    return await get_games(filter_dict=flter,start=start,stop=stop)


async def expire_stale_games_job() -> int:
    now = int(time.time())
    expirable_games = await get_expirable_games(before_timestamp=now - (10 * 60))
    game_ids = [game.id for game in expirable_games if game.id]
    for game in expirable_games:
        participants = [pid for pid in (game.creator_player_id, game.joiner_player_id) if pid]
        await reset_for_game_participants(participants)
    return await mark_games_expired(game_ids)


async def expire_game_if_needed(game: GameOut) -> GameOut:
    if game.status in {GameStatus.completed, GameStatus.expired}:
        return game
    if not game.settings.is_timed:
        return game

    created_at = game.date_created or 0
    expires_at = created_at + (game.settings.how_many_minutes * 60)
    if expires_at > int(time.time()):
        return game

    await update_game(
        filter_dict={"_id": ObjectId(game.id)},
        game_data=GameUpdate(status=GameStatus.expired),
    )
    participants = [pid for pid in (game.creator_player_id, game.joiner_player_id) if pid]
    await reset_for_game_participants(participants)
    refreshed_game = await get_game({"_id": ObjectId(game.id)})
    return refreshed_game or game

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
    gameObj = await get_game(filter_dict=filter_dict)
    if gameObj.status==GameStatus.started and game_data.joiner_player_id !=None:
        raise HTTPException(status_code=409, detail="You can only join a game once after which it is either completed or expired nothing else can happen")
    if gameObj.creator_player_id ==game_data.joiner_player_id:
        raise HTTPException(status_code=409,detail="Creator of a game can't join the same game a different player should join")
    if gameObj.status == GameStatus.expired:
        raise HTTPException(status_code=401,detail="Game has expired no more updates can be done this way")
    result = await update_game(filter_dict, game_data)

    if not result:
        raise HTTPException(status_code=404, detail="Game not found or update failed")

    return result
