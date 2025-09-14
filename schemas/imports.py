from bson import ObjectId
from pydantic import GetJsonSchemaHandler
from pydantic import BaseModel, EmailStr, Field,model_validator,AfterValidator
from pydantic_core import core_schema
from datetime import datetime,timezone
from typing import Optional,List,Any,Annotated
from enum import Enum
import time

def validate_secret(v: str) -> str:
    if not v.isdigit():
        raise ValueError("Secret must contain only digits")
    if len(v) != 4:
        raise ValueError("Secret must be exactly 4 digits")
    if len(set(v)) != 4:
        raise ValueError("Secret digits must be unique")
    return v

SecretStr = Annotated[str, AfterValidator(validate_secret)]
class PlayerType(str,Enum):
    creator="Creator"
    joiner="Joiner"


class GameStatus(str,Enum):
    waiting="waiting"
    started="started"
    completed="completed"
    expired="expired"
    
class GameSettings(BaseModel):
    is_timed: bool
    how_many_minutes: int
    is_public: bool

    @model_validator(mode="after")
    def check_timing_rules(self):
        # self is already a GameSettings instance here
        if self.is_timed and self.how_many_minutes < 10:
            raise ValueError("If 'is_timed' is True, 'how_many_minutes' must be at least 10")
        if not self.is_timed and self.how_many_minutes != 0:
            raise ValueError("If 'is_timed' is False, 'how_many_minutes' must be 0")
        return self
    
    
class GameType(str,Enum):
    single_player="SinglePlayer"
    multiplayer="Multiplayer"


class MatchResult(int,Enum):
    win=1
    loss=0
    