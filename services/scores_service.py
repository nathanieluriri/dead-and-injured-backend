from __future__ import annotations

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.player import get_players
from repositories.scores import create_scores, delete_scores, get_scores, get_scores_for_players, get_scoress, update_scores
from schemas.scores import ScoresCreate, ScoresOut, ScoresUpdate


async def add_scores(scores_data: ScoresCreate) -> ScoresOut:
    return await create_scores(scores_data)


async def remove_scores(scores_id: str):
    if not ObjectId.is_valid(scores_id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(scores_id)}
    result = await delete_scores(filter_dict)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scores not found")


async def retrieve_scores_by_scores_id(id: str) -> ScoresOut:
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_scores(filter_dict)
    if not result:
        raise HTTPException(status_code=404, detail="Scores not found")
    return result


async def retrieve_scoress(start=0, stop=100) -> List[ScoresOut]:
    return await get_scoress(start=start, stop=stop)


async def update_scores_by_id(scores_id: str, scores_data: ScoresUpdate) -> ScoresOut:
    if not ObjectId.is_valid(scores_id):
        raise HTTPException(status_code=400, detail="Invalid scores ID format")

    filter_dict = {"_id": ObjectId(scores_id)}
    result = await update_scores(filter_dict, scores_data)
    if not result:
        raise HTTPException(status_code=404, detail="Scores not found or update failed")
    return result


async def retrieve_scores_for_user(user_id: str) -> List[ScoresOut]:
    players = await get_players(filter_dict={"user_id": user_id}, start=0, stop=500)
    player_ids = [player.id for player in players if player.id]
    return await get_scores_for_players(player_ids)


async def retrieve_score_stats_for_user(user_id: str) -> dict[str, float | int]:
    scores = await retrieve_scores_for_user(user_id)
    wins = sum(1 for score in scores if int(score.match_result) == 1)
    losses = sum(1 for score in scores if int(score.match_result) == 0)
    total = wins + losses
    win_rate = round((wins / total) * 100, 2) if total else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "total_matches": total,
        "win_rate": win_rate,
    }
