from bson import ObjectId
from pydantic import GetJsonSchemaHandler
from pydantic import BaseModel, EmailStr, Field,model_validator
from pydantic_core import core_schema
from datetime import datetime,timezone
from typing import Optional,List,Any
from enum import Enum

class PlayerType(str,Enum):
    creator="Creator"
    joiner="Joiner"


class GameStatus(str,Enum):
    waiting="Waiting"
    started="Started"
    completed="Completed"
    
class GameType(str,Enum):
    single_player="SinglePlayer"
    multiplayer="Multiplayer"


class MatchResult(int,Enum):
    win=1
    loss=0
    