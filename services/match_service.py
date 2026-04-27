from __future__ import annotations

from bson import ObjectId
from fastapi import HTTPException
from typing import List

import logging
import time

from core.background_task import rebuild_leaderboard_task
from core.database import db
from repositories.game import get_game, update_game
from services.game_service import expire_game_if_needed
from services.match_modifier_service import clear_modifiers_for_game, consume_modifier, has_modifier
from services.presence_service import reset_for_game_participants
from repositories.match import create_match, delete_match, get_latest_match, get_match, get_matchs, update_match
from repositories.secret import get_secret
from repositories.scores import create_scores
from schemas.game import GameStatus, GameUpdate
from schemas.match import MatchBase, MatchCreate, MatchOut, MatchResult, MatchUpdate, Player
from schemas.scores import ScoresBase, ScoresCreate

logger = logging.getLogger(__name__)


async def _complete_game(game_id: str, winner_player_id: str, loser_player_id: str) -> None:
    await update_game(
        filter_dict={"_id": ObjectId(game_id)},
        game_data=GameUpdate(status=GameStatus.completed, last_player_id=winner_player_id),
    )
    await create_scores(scores_data=ScoresCreate(**ScoresBase(player_id=winner_player_id, match_result=MatchResult.win).model_dump()))
    await create_scores(scores_data=ScoresCreate(**ScoresBase(player_id=loser_player_id, match_result=MatchResult.loss).model_dump()))
    winner = await db.players.find_one({"_id": ObjectId(winner_player_id)}) if ObjectId.is_valid(winner_player_id) else None
    loser = await db.players.find_one({"_id": ObjectId(loser_player_id)}) if ObjectId.is_valid(loser_player_id) else None
    if winner is not None:
        winner_user_id = str(winner.get("user_id", ""))
        if winner_user_id and not winner_user_id.startswith(("guest:", "local:")) and winner_user_id != "bot":
            wallet = await db.wallets.find_one({"user_id": winner_user_id})
            if wallet is not None:
                await db.wallets.find_one_and_update(
                    {"_id": wallet["_id"]},
                    {"$set": {"balance": int(wallet.get("balance", 0)) + 40, "updated_at": int(time.time())}},
                )
            await db.notifications.insert_one(
                {
                    "user_id": winner_user_id,
                    "kind": "match_win",
                    "title": "Match won",
                    "body": "You earned 40 coins for a win.",
                    "unread": True,
                    "created_at": int(time.time()),
                }
            )
    if loser is not None:
        loser_user_id = str(loser.get("user_id", ""))
        if loser_user_id and not loser_user_id.startswith(("guest:", "local:")) and loser_user_id != "bot":
            await db.notifications.insert_one(
                {
                    "user_id": loser_user_id,
                    "kind": "match_loss",
                    "title": "Match complete",
                    "body": "Review the board and queue up the next round.",
                    "unread": True,
                    "created_at": int(time.time()),
                }
            )
    await reset_for_game_participants([winner_player_id, loser_player_id])
    try:
        rebuild_leaderboard_task.delay([])
    except Exception as err:
        logger.warning("Failed to enqueue leaderboard rebuild: %s", err)


async def _record_match(current_game, match_data: MatchBase) -> MatchOut:
    if current_game.creator_player_id == match_data.player_id:
        opponent_player_id = current_game.joiner_player_id
    elif current_game.joiner_player_id == match_data.player_id:
        opponent_player_id = current_game.creator_player_id
    else:
        raise HTTPException(status_code=403, detail="Player is not part of this game")

    opponents_secret = await get_secret(filter_dict={"player_id": opponent_player_id})
    if opponents_secret is None:
        raise HTTPException(status_code=404, detail="Opponent secret not found")

    player = Player(code=opponents_secret.secret)
    guess_result = player.guess_result(guess=match_data.guess)

    is_ghost = await consume_modifier(match_data.game_id, match_data.player_id, "ghost_guess")
    await consume_modifier(match_data.game_id, match_data.player_id, "fog")

    if guess_result.dead == 4:
        await _complete_game(
            game_id=match_data.game_id,
            winner_player_id=match_data.player_id,
            loser_player_id=opponent_player_id,
        )
        await clear_modifiers_for_game(match_data.game_id)
    else:
        has_extra_turn = await consume_modifier(match_data.game_id, match_data.player_id, "extra_turn")
        next_last_player_id = current_game.last_player_id if has_extra_turn else match_data.player_id
        await update_game(
            filter_dict={"_id": ObjectId(match_data.game_id)},
            game_data=GameUpdate(last_player_id=next_last_player_id),
        )

    created_match = await create_match(
        match_data=MatchCreate(
            player_id=match_data.player_id,
            game_id=match_data.game_id,
            guess=match_data.guess,
            dead=guess_result.dead,
            injured=guess_result.injured,
        )
    )
    if is_ghost and created_match.id and ObjectId.is_valid(created_match.id):
        await db.matchs.find_one_and_update({"_id": ObjectId(created_match.id)}, {"$set": {"ghost": True}})
    await db.match_events.insert_one(
        {
            "game_id": match_data.game_id,
            "event": "end" if guess_result.dead == 4 else "guess",
            "payload": {
                "player_id": match_data.player_id,
                "guess": match_data.guess,
                "dead": guess_result.dead,
                "injured": guess_result.injured,
            },
            "created_at": int(time.time()),
        }
    )
    return created_match


async def add_match(match_data: MatchBase) -> MatchOut:
    current_game = await get_game(filter_dict={"_id": ObjectId(match_data.game_id)})
    if current_game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    current_game = await expire_game_if_needed(current_game)
    if current_game.status != GameStatus.started:
        raise HTTPException(status_code=403, detail=f"Game status is {current_game.status}; guesses require started status")
    if match_data.player_id not in {current_game.creator_player_id, current_game.joiner_player_id}:
        raise HTTPException(status_code=403, detail="Player is not allowed to play in this game")
    if current_game.last_player_id == match_data.player_id:
        opponent_id = (
            current_game.joiner_player_id
            if match_data.player_id == current_game.creator_player_id
            else current_game.creator_player_id
        )
        skip_consumed = bool(opponent_id) and await consume_modifier(match_data.game_id, opponent_id, "skip_turn")
        if not skip_consumed:
            raise HTTPException(status_code=403, detail="Not your turn to play")

    last_match = await get_latest_match(game_id=match_data.game_id)
    if last_match is None and current_game.creator_player_id != match_data.player_id:
        raise HTTPException(status_code=403, detail="The creator must take the first turn")

    return await _record_match(current_game=current_game, match_data=match_data)


async def remove_match(match_id: str):
    if not ObjectId.is_valid(match_id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(match_id)}
    result = await delete_match(filter_dict)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Match not found")


async def retrieve_match_by_match_id(id: str) -> MatchOut:
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_match(filter_dict)
    if not result:
        raise HTTPException(status_code=404, detail="Match not found")
    return result


async def retrieve_matchs(gameId, start=0, stop=100) -> List[MatchOut]:
    return await get_matchs(filter_dict={"game_id": gameId}, start=start, stop=stop)


async def update_match_by_id(match_id: str, match_data: MatchUpdate) -> MatchOut:
    if not ObjectId.is_valid(match_id):
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    filter_dict = {"_id": ObjectId(match_id)}
    result = await update_match(filter_dict, match_data)
    if not result:
        raise HTTPException(status_code=404, detail="Match not found or update failed")
    return result
