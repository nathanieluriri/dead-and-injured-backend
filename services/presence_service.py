from __future__ import annotations

import time

from core.database import db


def _is_real_user(user_id: str | None) -> bool:
    if not user_id:
        return False
    if user_id == "bot":
        return False
    if user_id.startswith("guest:") or user_id.startswith("local:"):
        return False
    return True


async def _write_status(user_id: str, status: str) -> None:
    if not _is_real_user(user_id):
        return
    await db.presence.find_one_and_update(
        {"user_id": user_id},
        {"$set": {"last_seen": int(time.time()), "status": status}},
        upsert=True,
    )


async def set_in_queue(user_id: str) -> None:
    await _write_status(user_id, "In ranked queue")


async def set_in_match(user_id: str) -> None:
    await _write_status(user_id, "In match")


async def set_online(user_id: str) -> None:
    await _write_status(user_id, "Online")


async def _apply_status_to_players(player_ids: list[str], status: str) -> None:
    if not player_ids:
        return
    from bson import ObjectId

    valid_ids = [ObjectId(pid) for pid in player_ids if ObjectId.is_valid(pid)]
    if not valid_ids:
        return
    cursor = db.players.find({"_id": {"$in": valid_ids}}, {"user_id": 1})
    async for doc in cursor:
        await _write_status(str(doc.get("user_id", "")), status)


async def reset_for_game_participants(player_ids: list[str]) -> None:
    await _apply_status_to_players(player_ids, "Online")


async def set_in_match_for_game_participants(player_ids: list[str]) -> None:
    await _apply_status_to_players(player_ids, "In match")
