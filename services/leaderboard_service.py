from __future__ import annotations

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from core.database import db
from core.redis_cache import cache_delete, cache_get_json, cache_set_json
from repositories.leaderboard import clear_leaderboard, delete_leaderboard, get_leaderboard, get_leaderboards, update_leaderboard, upsert_leaderboard_entry
from repositories.user import get_users
from schemas.leaderboard import LeaderboardOut, LeaderboardUpdate
from services.scores_service import retrieve_score_stats_for_user


async def remove_leaderboard(leaderboard_id: str):
    if not ObjectId.is_valid(leaderboard_id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(leaderboard_id)}
    result = await delete_leaderboard(filter_dict)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Leaderboard not found")


async def retrieve_leaderboard_by_leaderboard_id(id: str) -> LeaderboardOut:
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_leaderboard(filter_dict)
    if not result:
        raise HTTPException(status_code=404, detail="Leaderboard not found")
    return result


async def retrieve_leaderboards(start=0, stop=100) -> List[LeaderboardOut]:
    return await get_leaderboards(start=start, stop=stop)


async def update_leaderboard_by_id(leaderboard_id: str, leaderboard_data: LeaderboardUpdate) -> LeaderboardOut:
    if not ObjectId.is_valid(leaderboard_id):
        raise HTTPException(status_code=400, detail="Invalid leaderboard ID format")

    filter_dict = {"_id": ObjectId(leaderboard_id)}
    result = await update_leaderboard(filter_dict, leaderboard_data)
    if not result:
        raise HTTPException(status_code=404, detail="Leaderboard not found or update failed")
    return result


async def rebuild_leaderboard(user_ids: list[str] | None = None) -> int:
    users = await get_users(start=0, stop=1000)
    if user_ids:
        allowed_ids = set(user_ids)
        users = [user for user in users if user.id in allowed_ids]

    ranking_rows: list[tuple[str, str, int]] = []
    for user in users:
        stats = await retrieve_score_stats_for_user(user.id)
        ranking_rows.append((user.id, user.email, int(stats["wins"])))

    ranking_rows.sort(key=lambda row: row[2], reverse=True)

    if not user_ids:
        await clear_leaderboard()

    for index, (user_id, email, wins) in enumerate(ranking_rows, start=1):
        await upsert_leaderboard_entry(user_id=user_id, email=email, wins=wins, rank=index)

    cache_delete("leaderboard:global")
    return len(ranking_rows)


async def retrieve_global_leaderboard(limit: int = 50, offset: int = 0) -> list[LeaderboardOut]:
    cache_key = f"leaderboard:global:{limit}:{offset}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return [LeaderboardOut.model_validate(item) for item in cached]

    cursor = db.leaderboards.find({}).sort("rank", 1).skip(offset).limit(limit)
    items: list[LeaderboardOut] = []
    async for doc in cursor:
        items.append(LeaderboardOut(**doc))
    cache_set_json(cache_key, [item.model_dump() for item in items], ttl_seconds=60)
    return items


async def retrieve_my_leaderboard(user_id: str) -> LeaderboardOut:
    result = await get_leaderboard({"user_id": user_id})
    if result is None:
        await rebuild_leaderboard([user_id])
        result = await get_leaderboard({"user_id": user_id})
    if result is None:
        raise HTTPException(status_code=404, detail="Leaderboard entry not found")
    return result
