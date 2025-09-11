# ============================================================================
#MATCH SCHEMA 
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:51:38 WAT
# It contains Pydantic classes  database
# for managing attributes and validation of data in and out of the MongoDB database.
#
# ============================================================================

from schemas.imports import *
from pydantic import Field
import time

class MatchBase(BaseModel):
    player_id:str
    game_id:str
    
    pass

class MatchCreate(MatchBase):
    # Add other fields here 
    date_created: int = Field(default_factory=lambda: int(time.time()))
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class MatchUpdate(BaseModel):
    # Add other fields here 
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class MatchOut(MatchBase):
    # Add other fields here 
    id: Optional[str] =None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None
    dead:int
    injured:int
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