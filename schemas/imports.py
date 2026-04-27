from bson import ObjectId
from pydantic import GetJsonSchemaHandler
from pydantic import BaseModel, EmailStr, Field,model_validator,AfterValidator
from pydantic_core import core_schema
from datetime import datetime,timezone
from typing import Optional,List,Any,Annotated
from enum import Enum
import time

from schemas.validators import CodeStr as SecretStr, validate_code as validate_secret
class PlayerType(str,Enum):
    creator="Creator"
    joiner="Joiner"


class GameStatus(str,Enum):
    waiting="waiting"
    started="started"
    completed="completed"
    expired="expired"
    
class GameType(str,Enum):
    single_player="SinglePlayer"
    multiplayer="Multiplayer"

class GameSettings(BaseModel):
    is_timed: bool
    how_many_minutes: int
    is_public: bool
    game_type:GameType

    @model_validator(mode="after")
    def check_timing_rules(self):
        # self is already a GameSettings instance here
        if self.is_timed and self.how_many_minutes < 10:
            raise ValueError("If 'is_timed' is True, 'how_many_minutes' must be at least 10")
        if not self.is_timed and self.how_many_minutes != 0:
            raise ValueError("If 'is_timed' is False, 'how_many_minutes' must be 0")
        return self
    
    


class MatchResult(int,Enum):
    win=1
    loss=0
    
    

class GuessResult(BaseModel):
    dead:int
    injured:int
    game_over:bool        
        
class Player:
    def __init__(self, code: SecretStr):
        """Initialize a player with a secret code (string of 4 digits)."""
        self.code = [int(d) for d in code]
        self.gameover = False

    def guess_result(self, guess: SecretStr)->GuessResult:
        """
        Calculates the result of a guess and returns a guess result object
        containing the number of dead (Bulls) and injured(Cows) code guesses

        Args:
            guess (SecretStr): _description_

        Returns:
            GuessResult: _description_
        """
        guess_digits = [int(d) for d in guess]

        # dead (bulls): correct digit & position
        dead = sum(g == c for g, c in zip(guess_digits, self.code))

        # injured (cows): correct digit anywhere but not counted in the accurate position
        injured = (
            sum(min(guess_digits.count(d), self.code.count(d)) for d in set(guess_digits))
            - dead
        )

        if dead == len(self.code):
            self.gameover = True
            
        return GuessResult(dead=dead,injured=injured,game_over=self.gameover)
        


