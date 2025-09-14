# ============================================================================
#PLAYER SCHEMA 
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:51:44 WAT
# It contains Pydantic classes  database
# for managing attributes and validation of data in and out of the MongoDB database.
#
# ============================================================================

from schemas.imports import *
from pydantic import Field
import time


class PlayerBase(BaseModel):
    user_id:str
    game_id:Optional[str]=None
    player_type:PlayerType
    pass

class PlayerCreate(PlayerBase):
    # Add other fields here 
    date_created: int = Field(default_factory=lambda: int(time.time()))
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class PlayerUpdate(BaseModel):
    # Add other fields here 
    game_id:str
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class PlayerOut(PlayerBase):
    # Add other fields here 
    id: Optional[str] =None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None
    
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