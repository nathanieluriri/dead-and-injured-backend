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
    get_latest_match,
    delete_match,
)

from repositories.game import (
    get_game,update_game
)
from repositories.secret import (
    get_secret
)
from schemas.match import MatchCreate, MatchUpdate, MatchOut,MatchBase,GuessResult,Player
from schemas.game import GameStatus,GameUpdate





async def add_match(match_data: MatchBase) -> MatchOut:
    """adds an entry of MatchCreate to the database and returns an object but it runs through some logic before adding anything 
    It checks which player's turn after checking for turn it check if the player is even allowed and after checking it now checks if the game has started then after that it calculates dead and injured using an algorithm and then it allows players to add the match to the database
    

    Returns:
        _type_: MatchOut
    """
    # Check who's turn 
    last_match =await get_latest_match(game_id=match_data.game_id)
    
    if last_match:
        
        if last_match.player_id != match_data.player_id:
            current_game =  await get_game(filter_dict={"_id":ObjectId(match_data.game_id)})
            if (current_game.status !=GameStatus.started):
                raise HTTPException(status_code=403,detail=f"the game status is supposed to be started but currently its {current_game.status} and you can only play when the status is 'started' ")
            
            if (current_game.creator_player_id == match_data.player_id) and (current_game.status ==GameStatus.started):
                # calculate dead and injured Creator
                opponents_secret =await get_secret(filter_dict={"player_id":current_game.joiner_player_id})
                
                
                player = Player(code= opponents_secret.secret)
                guess_result =  player.guess_result(guess=match_data.guess)
                if guess_result.dead==4:
                # do something concerning win
                
                    
                    completed_game = GameUpdate(status=GameStatus.completed)
                    update_game(filter_dict={"_id":ObjectId(match_data.game_id)},game_data=completed_game)
                    # TODO: Add the winning player's score to the score table 
                    pass
                
                new_match_create_data = MatchCreate(player_id=match_data.player_id,game_id=match_data.game_id,guess=match_data.guess,dead=guess_result.dead,injured=guess_result.injured)
                return await create_match(match_data=new_match_create_data)
            
            
            elif (current_game.joiner_player_id == match_data.player_id) and (current_game.status ==GameStatus.started):
                # calculate dead and injured Joiner
                
                opponents_secret =await get_secret(filter_dict={"player_id":current_game.creator_player_id})
                
                
                player = Player(code= opponents_secret.secret)
                guess_result =  player.guess_result(guess=match_data.guess)
                if guess_result.dead==4:
                # do something concerning win
                
                    
                    completed_game = GameUpdate(status=GameStatus.completed)
                    update_game(filter_dict={"_id":ObjectId(match_data.game_id)},game_data=completed_game)
                    # TODO: Add the winning player's score to the score table 
                    pass
                
                new_match_create_data = MatchCreate(player_id=match_data.player_id,game_id=match_data.game_id,guess=match_data.guess,dead=guess_result.dead,injured=guess_result.injured)
                return await create_match(match_data=new_match_create_data)
            
            else:
                raise HTTPException(status_code=403,detail="Player Id not allowed to join this game to play")     
        else:
            raise HTTPException(status_code=403,detail="Not your turn to play")
    else:
        current_game =  await get_game(filter_dict={"_id":ObjectId(match_data.game_id)})
        if (current_game.status !=GameStatus.started):
                raise HTTPException(status_code=403,detail=f"the game status is supposed to be started but currently its {current_game.status} and you can only play when the status is 'started' ")
        if (current_game.creator_player_id == match_data.player_id) and (current_game.status ==GameStatus.started):
            # Calculate dead and injured first round
            opponents_secret =await get_secret(filter_dict={"player_id":current_game.joiner_player_id})
            
            
            player = Player(code= opponents_secret.secret)
            guess_result =  player.guess_result(guess=match_data.guess)
            if guess_result.dead==4:
                # do something concerning win
                
                
                completed_game = GameUpdate(status=GameStatus.completed)
                update_game(filter_dict={"_id":ObjectId(match_data.game_id)},game_data=completed_game)
                # TODO: Add the winning player's score to the score table 
                pass
            
            new_match_create_data = MatchCreate(player_id=match_data.player_id,game_id=match_data.game_id,guess=match_data.guess,dead=guess_result.dead,injured=guess_result.injured)
            return await create_match(match_data=new_match_create_data)
        
        elif (current_game.joiner_player_id == match_data.player_id) and (current_game.status ==GameStatus.started):
             raise HTTPException(status_code=403,detail="Not your turn to play")
        
        else:
                raise HTTPException(status_code=403,detail="Player Id not allowed to join this game to play") 
        
        
        
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


async def retrieve_matchs(gameId,start=0,stop=100) -> List[MatchOut]:
    """Retrieves MatchOut Objects in a list

    Returns:
        _type_: MatchOut
    """
    return await get_matchs(filter_dict={"game_id":gameId},start=start,stop=stop)


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