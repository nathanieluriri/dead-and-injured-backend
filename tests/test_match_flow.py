"""Integration tests for the match lifecycle (`add_match`) against a mock Mongo.

Regression coverage for the single-player turn soft-lock plus the multiplayer
turn-taking rules. Seeding goes through the same repository/service helpers the
app uses, so these exercise the real code paths.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from schemas.imports import GameSettings, GameStatus, GameType, PlayerType
from schemas.game import GameCreate, GameUpdate
from schemas.player import PlayerBase, PlayerCreate
from schemas.secret import SecretBase, SecretCreate
from schemas.match import MatchBase
from services.game_service import add_game, retrieve_game_by_game_id, update_game_by_id
from services.player_service import add_player
from services.secret_service import add_secret
from services.match_service import add_match


async def _seed(game_type, is_public, creator_uid, joiner_uid, creator_secret=None, joiner_secret=None):
    game = await add_game(
        GameCreate(
            status=GameStatus.waiting,
            settings=GameSettings(is_timed=False, how_many_minutes=0, is_public=is_public, game_type=game_type),
            creator_player_id=creator_uid,
        )
    )
    creator = await add_player(PlayerCreate(**PlayerBase(user_id=creator_uid, game_id=game.id, player_type=PlayerType.creator).model_dump()))
    joiner = await add_player(PlayerCreate(**PlayerBase(user_id=joiner_uid, game_id=game.id, player_type=PlayerType.joiner).model_dump()))
    if creator_secret:
        await add_secret(SecretCreate(**SecretBase(secret=creator_secret, player_id=creator.id).model_dump()))
    if joiner_secret:
        await add_secret(SecretCreate(**SecretBase(secret=joiner_secret, player_id=joiner.id).model_dump()))
    await update_game_by_id(
        game.id,
        GameUpdate(creator_player_id=creator.id, joiner_player_id=joiner.id, status=GameStatus.started, last_player_id=None),
    )
    return game.id, creator.id, joiner.id


async def test_single_player_allows_repeated_guesses():
    """Regression: vs-bot used to 403 on the second guess ('not your turn')."""
    gid, human, _bot = await _seed(GameType.single_player, False, "u_human", "bot", joiner_secret="1234")
    await add_match(MatchBase(player_id=human, game_id=gid, guess="5678"))  # 1st
    await add_match(MatchBase(player_id=human, game_id=gid, guess="5670"))  # 2nd must not raise
    await add_match(MatchBase(player_id=human, game_id=gid, guess="9012"))  # 3rd must not raise


async def test_single_player_win_completes_game():
    gid, human, _bot = await _seed(GameType.single_player, False, "u_human", "bot", joiner_secret="1234")
    await add_match(MatchBase(player_id=human, game_id=gid, guess="5678"))
    await add_match(MatchBase(player_id=human, game_id=gid, guess="1234"))  # correct
    game = await retrieve_game_by_game_id(gid)
    assert game.status == GameStatus.completed
    assert game.last_player_id == human  # winner recorded


async def test_multiplayer_blocks_repeated_guess():
    gid, a, _b = await _seed(GameType.multiplayer, True, "u_a", "u_b", creator_secret="1234", joiner_secret="5678")
    await add_match(MatchBase(player_id=a, game_id=gid, guess="9012"))  # creator's first turn
    with pytest.raises(HTTPException) as exc:
        await add_match(MatchBase(player_id=a, game_id=gid, guess="9013"))  # again -> blocked
    assert exc.value.status_code == 403


async def test_multiplayer_alternates_turns():
    gid, a, b = await _seed(GameType.multiplayer, True, "u_a", "u_b", creator_secret="1234", joiner_secret="5678")
    await add_match(MatchBase(player_id=a, game_id=gid, guess="9012"))  # creator
    await add_match(MatchBase(player_id=b, game_id=gid, guess="9012"))  # joiner now allowed


async def test_joiner_cannot_take_first_turn():
    gid, _a, b = await _seed(GameType.multiplayer, True, "u_c", "u_d", creator_secret="1234", joiner_secret="5678")
    with pytest.raises(HTTPException) as exc:
        await add_match(MatchBase(player_id=b, game_id=gid, guess="9012"))
    assert exc.value.status_code == 403
