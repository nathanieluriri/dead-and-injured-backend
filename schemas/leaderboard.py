# ============================================================================
#LEADERBOARD SCHEMA 
# ============================================================================
# This file was auto-generated on: 2025-09-10 09:55:37 WAT
# It contains Pydantic classes  database
# for managing attributes and validation of data in and out of the MongoDB database.
#
# ============================================================================

from schemas.imports import *
from pydantic import Field
import time


class LeaderboardBase(BaseModel):
    # Add other fields here 
    user_id:str
    email:EmailStr
    wins:int
    rank:int
    pass

class LeaderboardCreate(LeaderboardBase):
    # Add other fields here 
    date_created: int = Field(default_factory=lambda: int(time.time()))
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class LeaderboardUpdate(BaseModel):
    # Add other fields here 
    last_updated: int = Field(default_factory=lambda: int(time.time()))

class LeaderboardOut(LeaderboardBase):
    # Add other fields here 
    id: Optional[str] =None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None
    
    @model_validator(mode='before')
    def set_dynamic_values(cls,values):
        if isinstance(values, dict) and values.get('_id') is not None:
            values['id'] = str(values['_id'])
        return values
    class Config:
        from_attributes = True
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
