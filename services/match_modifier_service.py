from __future__ import annotations

import time
from typing import Literal

from core.database import db


ModifierType = Literal["skip_turn", "extra_turn", "shield", "fake_feedback", "ghost_guess", "fog"]
OFFENSIVE_MODIFIERS: set[str] = {"skip_turn", "fake_feedback", "fog"}


async def add_modifier(game_id: str, target_player_id: str, source_player_id: str, modifier_type: ModifierType) -> None:
    await db.match_modifiers.insert_one(
        {
            "game_id": game_id,
            "target_player_id": target_player_id,
            "source_player_id": source_player_id,
            "type": modifier_type,
            "created_at": int(time.time()),
        }
    )


async def consume_modifier(game_id: str, target_player_id: str, modifier_type: ModifierType) -> bool:
    result = await db.match_modifiers.find_one_and_delete(
        {
            "game_id": game_id,
            "target_player_id": target_player_id,
            "type": modifier_type,
        },
        sort=[("created_at", 1)],
    )
    return result is not None


async def has_modifier(game_id: str, target_player_id: str, modifier_type: ModifierType) -> bool:
    result = await db.match_modifiers.find_one(
        {
            "game_id": game_id,
            "target_player_id": target_player_id,
            "type": modifier_type,
        }
    )
    return result is not None


async def apply_offensive_modifier(
    game_id: str,
    target_player_id: str,
    source_player_id: str,
    modifier_type: ModifierType,
) -> bool:
    """Add offensive modifier unless target has shield. Returns True if applied, False if blocked."""
    if modifier_type not in OFFENSIVE_MODIFIERS:
        raise ValueError(f"{modifier_type} is not an offensive modifier")
    blocked = await consume_modifier(game_id, target_player_id, "shield")
    if blocked:
        return False
    await add_modifier(game_id, target_player_id, source_player_id, modifier_type)
    return True


async def clear_modifiers_for_game(game_id: str) -> None:
    await db.match_modifiers.delete_many({"game_id": game_id})
