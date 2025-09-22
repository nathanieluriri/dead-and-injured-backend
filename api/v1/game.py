
from fastapi import APIRouter, HTTPException, Query, status, Path,Depends
from typing import List
from bson import ObjectId
from schemas.response_schema import APIResponse
from schemas.tokens_schema import accessTokenOut
from schemas.game import (
    GameCreate,
    GameOut,
    GameBase,
    GameUpdate,
    GameStatus,
)
from schemas.player import (
    PlayerCreate,
    PlayerBase,
    PlayerOut,
    PlayerType,
    PlayerUpdate
)
from schemas.secret import (
 SecretBase,
 SecretCreate,   
)
from services.game_service import (
    add_game,
    remove_game,
    retrieve_available_games,
    retrieve_game_by_game_id,
    update_game_by_id,
)
from services.player_service import (
    add_player,
   
)
from services.secret_service import (
    add_secret,
   
)
from security.auth import verify_token
from pydantic import AfterValidator
from typing import Annotated

def validate_secret(v: str) -> str:
    if not v.isdigit():
        raise ValueError("Secret must contain only digits")
    if len(v) != 4:
        raise ValueError("Secret must be exactly 4 digits")
    if len(set(v)) != 4:
        raise ValueError("Secret digits must be unique")
    return v

SecretStr = Annotated[str, AfterValidator(validate_secret)]
router = APIRouter(prefix="/games", tags=["Games"])



@router.get("/{start}/{stop}",dependencies=[Depends(verify_token)],description="You can only view games that are set to public anyone can join those games and are in the waiting status", response_model=APIResponse[List[GameOut]])
async def list_games(start:int= 0, stop:int=100):
    items = await retrieve_available_games(start,stop)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me",description="You can use this to view histories of games as long as they are viewable to you", response_model=APIResponse[GameOut])
async def get_my_games(id: str = Query(..., description="game ID to fetch specific item")):
    items = await retrieve_game_by_game_id(id=id)
    return APIResponse(status_code=200, data=items, detail="games items fetched")


@router.post("/{secret}",description="You can use this to create new games ",dependencies=[Depends(verify_token)], response_model=APIResponse[ GameOut])
async def create_new_game(secret:SecretStr,game_data:GameBase,token:accessTokenOut = Depends(verify_token)):
    
    new_game = GameCreate(status=GameStatus.waiting,settings=game_data.settings,creator_player_id=token.userId)

    items = await add_game(game_data=new_game)
    
    player_data = PlayerBase(user_id=token.userId,game_id=items.id,player_type=PlayerType.creator)
    new_player_data = PlayerCreate(**player_data.model_dump())
    creator_player =await add_player(player_data=new_player_data)
    secret_base = SecretBase(secret=secret,player_id=creator_player.id)
    new_secret= SecretCreate(**secret_base.model_dump())
    await add_secret(secret_data=new_secret)
    game_update_data = GameUpdate(creator_player_id=creator_player.id)
    await update_game_by_id(game_id=items.id,game_data=game_update_data)
    items = await retrieve_game_by_game_id(id=items.id)
    
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")



@router.post("/join/{gameId}/{secret}",description="You can use this to Join new games ",dependencies=[Depends(verify_token)], response_model=APIResponse[GameOut])
async def create_new_game(secret:SecretStr,gameId:str,token:accessTokenOut = Depends(verify_token)):
  
 
    player_data = PlayerBase(user_id=token.userId,game_id=gameId,player_type=PlayerType.joiner)
    
    new_player_data = PlayerCreate(**player_data.model_dump())
    
    joiner_player =await add_player(player_data=new_player_data)
    game_update_data = GameUpdate(joiner_player_id=joiner_player.id,status=GameStatus.started)
    await update_game_by_id(game_id=gameId,game_data=game_update_data)
    secret =SecretBase(secret=secret,player_id=joiner_player.id)
    new_secret = SecretCreate(**secret.model_dump())
    await add_secret(secret_data=new_secret)
    items = await retrieve_game_by_game_id(id=gameId)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")



# TODO: Create an SSE Event to notify players in multiplayer mode of game state changes 