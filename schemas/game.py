# ============================================================================
#GAME SCHEMA 
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:51:57 WAT
# It contains Pydantic classes  database
# for managing attributes and validation of data in and out of the MongoDB database.
#
# ============================================================================

from schemas.imports import *
from typing import Annotated
from pydantic import BaseModel, StringConstraints, field_validator
import time

class GameBase(BaseModel):
    # Add other fields here 
    settings:GameSettings
    pass

class GameCreate(GameBase):
    # Add other fields here
    
    status:GameStatus
    creator_player_id:str 
    date_created: int = Field(default_factory=lambda: int(time.time()))
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class GameUpdate(BaseModel):
    # Add other fields here
    creator_player_id:Optional[str]=None
    joiner_player_id:Optional[str]=None
    status:Optional[GameStatus ]=None
    last_updated: int = Field(default_factory=lambda: int(time.time()))



class GameOut(GameBase):
    # Add other fields here
    status:GameStatus
     
    id: Optional[str] =None
    joiner_player_id:Optional[str]=None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None
    creator_player_id:Optional[str]=None
    @model_validator(mode='before')
    def set_dynamic_values(cls,values):
      
        values['id']= str(values.get('_id'))
        return values
    class Config:
        from_attributes = True
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }