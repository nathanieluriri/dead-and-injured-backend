from __future__ import annotations

import json
import random
import time
from typing import Literal

from bson import ObjectId
from fastapi import HTTPException

from core.database import db
from core.matchmaking_events import publish as publish_matchmaking_event
from schemas.app_features import (
    LocalGameCreateRequest,
    MatchGuessResponse,
    MatchSessionGuess,
    MatchSessionOpponent,
    MatchSessionResponse,
    MatchmakingQueueResponse,
    PowerUpItem,
    PowerUpReveal,
    PowerUpUseResponse,
)
from schemas.game import GameCreate, GameSettings, GameStatus, GameType, GameUpdate
from schemas.match import MatchBase
from schemas.player import PlayerBase, PlayerCreate, PlayerType
from schemas.secret import SecretBase, SecretCreate
from services.app_features_service import get_inventory
from services.game_service import add_game, expire_game_if_needed, retrieve_game_by_game_id, update_game_by_id
from services.match_modifier_service import add_modifier, apply_offensive_modifier, consume_modifier, has_modifier
from services.presence_service import set_in_match, set_in_match_for_game_participants, set_in_queue, set_online
from services.match_service import add_match, retrieve_matchs
from services.player_service import add_player, retrieve_player_by_player_id, retrieve_player_for_user_in_game
from services.secret_service import add_secret


def _secret_value(length: int = 4) -> str:
    return "".join(random.sample("0123456789", length))


def _mode_from_game_doc(game: dict) -> Literal["bot", "online", "friend", "local", "practice", "puzzle"]:
    if game.get("mode") in {"bot", "online", "friend", "local", "practice", "puzzle"}:
        return game["mode"]
    if game.get("settings", {}).get("game_type") == "SinglePlayer":
        return "bot"
    if game.get("settings", {}).get("is_public"):
        return "online"
    return "friend"


def _subtitle_from_mode(mode: str) -> str:
    if mode == "bot":
        return "Server-authoritative bot"
    if mode == "online":
        return "Ranked queue match"
    if mode == "local":
        return "Shared device"
    if mode == "practice":
        return "Practice sandbox"
    if mode == "puzzle":
        return "Puzzle challenge"
    return "Private challenge"


async def _raw_game(game_id: str) -> dict:
    if not ObjectId.is_valid(game_id):
        raise HTTPException(status_code=400, detail="Invalid game id")
    game = await db.games.find_one({"_id": ObjectId(game_id)})
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.get("status") in {GameStatus.waiting.value, GameStatus.started.value}:
        from schemas.game import GameOut

        refreshed = await expire_game_if_needed(GameOut(**game))
        if refreshed and refreshed.status == GameStatus.expired:
            game = await db.games.find_one({"_id": ObjectId(game_id)}) or game
    return game


async def _set_game_mode(game_id: str, mode: str) -> None:
    await db.games.find_one_and_update({"_id": ObjectId(game_id)}, {"$set": {"mode": mode, "last_updated": int(time.time())}})


async def _load_powerups(user_id: str | None) -> list[PowerUpItem]:
    if not user_id or user_id == "bot" or user_id.startswith("guest:") or user_id.startswith("local:"):
        return []
    inventory = await get_inventory(user_id)
    return [item for item in inventory if item.count > 0][:5]


async def _player_name(player_id: str | None) -> tuple[str, str]:
    if not player_id or not ObjectId.is_valid(player_id):
        return ("Unknown", "UN")
    player = await retrieve_player_by_player_id(player_id)
    user_id = player.user_id
    if user_id == "bot":
        return ("Bot", "BT")
    if user_id.startswith("local:"):
        return ("Pass & Play", "LP")
    if user_id.startswith("guest:"):
        return ("Guest", "GS")
    if not ObjectId.is_valid(user_id):
        return ("Unknown", "UN")
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        return ("Unknown", "UN")
    username = str(user["username"])
    initials = "".join(part[0].upper() for part in username.replace(".", " ").split()[:2]) or username[:2].upper()
    return (username, initials)


async def create_single_player_game(user_id: str | None) -> MatchSessionResponse:
    owner_id = user_id or f"guest:{ObjectId()}"
    item = await add_game(
        GameCreate(
            status=GameStatus.waiting,
            settings=GameSettings(is_timed=False, how_many_minutes=0, is_public=False, game_type=GameType.single_player),
            creator_player_id=owner_id,
        )
    )
    creator_player = await add_player(PlayerCreate(**PlayerBase(user_id=owner_id, game_id=item.id, player_type=PlayerType.creator).model_dump()))
    bot_player = await add_player(PlayerCreate(**PlayerBase(user_id="bot", game_id=item.id, player_type=PlayerType.joiner).model_dump()))
    await add_secret(SecretCreate(**SecretBase(secret=_secret_value(), player_id=bot_player.id).model_dump()))
    await update_game_by_id(
        item.id,
        game_data=GameUpdate(
            creator_player_id=creator_player.id,
            joiner_player_id=bot_player.id,
            status=GameStatus.started,
            last_player_id=None,
        ),
    )
    await _set_game_mode(item.id, "bot")
    await set_in_match(owner_id)
    return await build_match_session(item.id, owner_id)


async def create_local_game(payload: LocalGameCreateRequest) -> MatchSessionResponse:
    owner_id = f"local:{ObjectId()}"
    item = await add_game(
        GameCreate(
            status=GameStatus.waiting,
            settings=GameSettings(is_timed=False, how_many_minutes=0, is_public=False, game_type=GameType.multiplayer),
            creator_player_id=owner_id,
        )
    )
    creator = await add_player(PlayerCreate(**PlayerBase(user_id=owner_id, game_id=item.id, player_type=PlayerType.creator).model_dump()))
    joiner = await add_player(PlayerCreate(**PlayerBase(user_id=f"{owner_id}:opponent", game_id=item.id, player_type=PlayerType.joiner).model_dump()))
    await add_secret(SecretCreate(**SecretBase(secret=payload.creator_secret, player_id=creator.id).model_dump()))
    await add_secret(SecretCreate(**SecretBase(secret=payload.joiner_secret, player_id=joiner.id).model_dump()))
    await update_game_by_id(
        item.id,
        game_data=GameUpdate(
            creator_player_id=creator.id,
            joiner_player_id=joiner.id,
            status=GameStatus.started,
            last_player_id=None,
        ),
    )
    await _set_game_mode(item.id, "local")
    return await build_match_session(item.id, owner_id)


async def join_matchmaking_queue(user_id: str) -> MatchmakingQueueResponse:
    await db.matchmaking_queue.delete_many({"user_id": user_id})
    waiting = await db.matchmaking_queue.find_one({"user_id": {"$ne": user_id}}, sort=[("created_at", 1)])
    if waiting is None:
        await db.matchmaking_queue.insert_one({"user_id": user_id, "created_at": int(time.time())})
        await set_in_queue(user_id)
        return MatchmakingQueueResponse(status="queued")

    opponent_id = waiting["user_id"]
    await db.matchmaking_queue.delete_one({"_id": waiting["_id"]})
    item = await add_game(
        GameCreate(
            status=GameStatus.waiting,
            settings=GameSettings(is_timed=False, how_many_minutes=0, is_public=True, game_type=GameType.multiplayer),
            creator_player_id=opponent_id,
        )
    )
    creator = await add_player(PlayerCreate(**PlayerBase(user_id=opponent_id, game_id=item.id, player_type=PlayerType.creator).model_dump()))
    joiner = await add_player(PlayerCreate(**PlayerBase(user_id=user_id, game_id=item.id, player_type=PlayerType.joiner).model_dump()))
    await update_game_by_id(
        item.id,
        game_data=GameUpdate(
            creator_player_id=creator.id,
            joiner_player_id=joiner.id,
            status=GameStatus.waiting,
            last_player_id=None,
        ),
    )
    await _set_game_mode(item.id, "online")
    await set_in_match(opponent_id)
    await set_in_match(user_id)
    opponent_name, _ = await _player_name(creator.id)
    joiner_name, _ = await _player_name(joiner.id)
    await publish_matchmaking_event(
        opponent_id,
        {
            "type": "match_found",
            "match_id": item.id,
            "opponent_name": joiner_name,
            "generatedAt": int(time.time()),
        },
    )
    return MatchmakingQueueResponse(status="matched", match_id=item.id, opponent_name=opponent_name)


async def leave_matchmaking_queue(user_id: str) -> dict[str, str]:
    await db.matchmaking_queue.delete_many({"user_id": user_id})
    await set_online(user_id)
    return {"status": "idle"}


async def get_active_friend_game(user_id: str) -> MatchSessionResponse | None:
    player_cursor = db.players.find({"user_id": user_id})
    game_ids: list[ObjectId] = []
    async for player in player_cursor:
        game_id_str = player.get("game_id")
        if game_id_str and ObjectId.is_valid(game_id_str):
            game_ids.append(ObjectId(game_id_str))
    if not game_ids:
        return None
    game = await db.games.find_one(
        {
            "_id": {"$in": game_ids},
            "mode": "friend",
            "status": {"$in": [GameStatus.waiting.value, GameStatus.started.value]},
        },
        sort=[("last_updated", -1)],
    )
    if game is None:
        return None
    return await build_match_session(str(game["_id"]), user_id)


async def get_matchmaking_status(user_id: str) -> MatchmakingQueueResponse:
    waiting = await db.matchmaking_queue.find_one({"user_id": user_id})
    if waiting is not None:
        return MatchmakingQueueResponse(status="queued")
    player = await db.players.find_one({"user_id": user_id}, sort=[("date_created", -1)])
    if player is None:
        return MatchmakingQueueResponse(status="idle")
    game = await db.games.find_one({"_id": ObjectId(player["game_id"])}) if ObjectId.is_valid(player["game_id"]) else None
    if game and game.get("mode") == "online" and game.get("status") in {"waiting", "started"}:
        opponent_player_id = game["joiner_player_id"] if game["creator_player_id"] == str(player["_id"]) else game["creator_player_id"]
        opponent_name, _ = await _player_name(opponent_player_id)
        return MatchmakingQueueResponse(status="matched", match_id=str(game["_id"]), opponent_name=opponent_name)
    return MatchmakingQueueResponse(status="idle")


async def submit_join_secret(game_id: str, user_id: str, secret: str) -> MatchSessionResponse:
    player = await retrieve_player_for_user_in_game(user_id=user_id, game_id=game_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found for game")
    secret_doc = await db.secrets.find_one({"player_id": player.id})
    if secret_doc is None:
        await add_secret(SecretCreate(**SecretBase(secret=secret, player_id=player.id).model_dump()))
    game = await _raw_game(game_id)
    creator_secret = await db.secrets.find_one({"player_id": game.get("creator_player_id")})
    joiner_secret = await db.secrets.find_one({"player_id": game.get("joiner_player_id")})
    next_status = GameStatus.started if creator_secret and joiner_secret else GameStatus.waiting
    await update_game_by_id(game_id, game_data=GameUpdate(status=next_status))
    if next_status == GameStatus.started:
        await set_in_match_for_game_participants(
            [pid for pid in (game.get("creator_player_id"), game.get("joiner_player_id")) if pid]
        )
    return await build_match_session(game_id, user_id)


async def build_match_session(game_id: str, viewer_user_id: str | None) -> MatchSessionResponse:
    game = await _raw_game(game_id)
    mode = _mode_from_game_doc(game)
    creator_player_id = game.get("creator_player_id")
    joiner_player_id = game.get("joiner_player_id")

    viewer_player_id: str | None = None
    if viewer_user_id:
        viewer = await db.players.find_one({"user_id": viewer_user_id, "game_id": game_id})
        if viewer is not None:
            viewer_player_id = str(viewer["_id"])
    if viewer_player_id is None:
        viewer_player_id = creator_player_id

    if viewer_player_id == creator_player_id:
        opponent_player_id = joiner_player_id
    else:
        opponent_player_id = creator_player_id

    opponent_name, opponent_initials = await _player_name(opponent_player_id)
    matches = await retrieve_matchs(game_id, 0, 100)
    ghost_ids: set[str] = set()
    async for doc in db.matchs.find({"game_id": game_id, "ghost": True}, {"_id": 1}):
        ghost_ids.add(str(doc["_id"]))
    fog_active = bool(viewer_player_id) and await has_modifier(game_id, viewer_player_id, "fog")
    viewer_match_indices = [i for i, m in enumerate(matches) if m.player_id == viewer_player_id]
    fog_blank_indices = set(viewer_match_indices[-2:]) if fog_active else set()

    history: list[MatchSessionGuess] = []
    for index, match in enumerate(matches):
        by_viewer = match.player_id == viewer_player_id
        is_ghost_to_viewer = (not by_viewer) and (match.id in ghost_ids)
        is_fogged = index in fog_blank_indices
        digits = [int(digit) for digit in match.guess]
        if is_ghost_to_viewer or is_fogged:
            digits = [-1, -1, -1, -1]
        history.append(
            MatchSessionGuess(
                attempt=index + 1,
                digits=digits,
                dead=match.dead,
                injured=match.injured,
                byViewer=by_viewer,
            )
        )
    viewer_player = await db.players.find_one({"_id": ObjectId(viewer_player_id)}) if viewer_player_id and ObjectId.is_valid(viewer_player_id) else None
    viewer_user_key = str(viewer_player["user_id"]) if viewer_player else None
    can_guess = game.get("status") == "started" and game.get("last_player_id") != viewer_player_id
    if not matches and viewer_player_id != creator_player_id:
        can_guess = False
    loadout = await _load_powerups(viewer_user_key)
    return MatchSessionResponse(
        id=game_id,
        mode=mode,
        status=str(game.get("status", "waiting")),
        canGuess=can_guess,
        viewerPlayerId=viewer_player_id,
        opponent=MatchSessionOpponent(
            initials=opponent_initials,
            name=opponent_name,
            subtitle=_subtitle_from_mode(mode),
        ),
        history=history,
        loadout=loadout,
        streamUrl=f"/api/v1/matches/{game_id}/stream",
        guessUrl=f"/api/v1/matches/{game_id}/guess",
        powerupUrl=f"/api/v1/matches/{game_id}/powerup",
    )


async def submit_guess(game_id: str, guess: str, viewer_user_id: str | None, viewer_player_id: str | None = None) -> MatchGuessResponse:
    if viewer_player_id is None:
        if viewer_user_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        player = await retrieve_player_for_user_in_game(user_id=viewer_user_id, game_id=game_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found for game")
        viewer_player_id = player.id
    fake_feedback_active = bool(viewer_player_id) and await has_modifier(game_id, viewer_player_id, "fake_feedback")
    match = await add_match(MatchBase(player_id=viewer_player_id, game_id=game_id, guess=guess))
    if fake_feedback_active:
        await consume_modifier(game_id, viewer_player_id, "fake_feedback")
        secret_length = len(match.guess)
        fake_dead = (match.dead + 1) % (secret_length + 1)
        fake_injured = max(0, secret_length - fake_dead - max(0, match.injured - 1))
        reported_dead, reported_injured, reported_solved = fake_dead, fake_injured, False
    else:
        reported_dead, reported_injured, reported_solved = match.dead, match.injured, match.dead == len(match.guess)
    game = await retrieve_game_by_game_id(game_id)
    return MatchGuessResponse(
        attempt=len(await retrieve_matchs(game_id, 0, 200)),
        dead=reported_dead,
        injured=reported_injured,
        solved=reported_solved,
        status=game.status.value if hasattr(game.status, "value") else str(game.status),
    )


async def _opponent_secret_digits(game_id: str, viewer_user_id: str) -> list[int]:
    viewer_player = await retrieve_player_for_user_in_game(user_id=viewer_user_id, game_id=game_id)
    if viewer_player is None:
        raise HTTPException(status_code=404, detail="Player not found for game")
    game = await _raw_game(game_id)
    creator_player_id = str(game.get("creator_player_id") or "")
    joiner_player_id = str(game.get("joiner_player_id") or "")
    if viewer_player.id == creator_player_id:
        opponent_player_id = joiner_player_id
    elif viewer_player.id == joiner_player_id:
        opponent_player_id = creator_player_id
    else:
        raise HTTPException(status_code=403, detail="Player is not part of this game")
    secret_doc = await db.secrets.find_one({"player_id": opponent_player_id})
    if secret_doc is None:
        raise HTTPException(status_code=404, detail="Opponent secret not available yet")
    return [int(d) for d in str(secret_doc["secret"])]


async def _build_reveal(powerup_id: str, game_id: str, viewer_user_id: str) -> tuple[PowerUpReveal | None, str]:
    if powerup_id == "peek-in":
        digits = await _opponent_secret_digits(game_id, viewer_user_id)
        digit = random.choice(digits)
        return PowerUpReveal(kind="peek-in", digit=digit), f"Digit {digit} is in the secret"
    if powerup_id == "peek-out":
        secret_set = set(await _opponent_secret_digits(game_id, viewer_user_id))
        outside = [d for d in range(10) if d not in secret_set]
        digit = random.choice(outside) if outside else 0
        return PowerUpReveal(kind="peek-out", digit=digit), f"Digit {digit} is not in the secret"
    if powerup_id == "pin":
        digits = await _opponent_secret_digits(game_id, viewer_user_id)
        position = random.randrange(len(digits))
        return PowerUpReveal(kind="pin", position=position), f"Position {position + 1} is locked in"
    if powerup_id == "lock-in":
        digits = await _opponent_secret_digits(game_id, viewer_user_id)
        position = random.randrange(len(digits))
        return PowerUpReveal(kind="lock-in", digit=digits[position], position=position), f"Digit {digits[position]} sits at position {position + 1}"
    return None, ""


async def _viewer_and_opponent_players(game_id: str, viewer_user_id: str) -> tuple[str, str]:
    viewer_player = await retrieve_player_for_user_in_game(user_id=viewer_user_id, game_id=game_id)
    if viewer_player is None:
        raise HTTPException(status_code=404, detail="Player not found for game")
    game = await _raw_game(game_id)
    creator_player_id = str(game.get("creator_player_id") or "")
    joiner_player_id = str(game.get("joiner_player_id") or "")
    if viewer_player.id == creator_player_id:
        return viewer_player.id, joiner_player_id
    if viewer_player.id == joiner_player_id:
        return viewer_player.id, creator_player_id
    raise HTTPException(status_code=403, detail="Player is not part of this game")


async def _apply_turn_modifier(powerup_id: str, game_id: str, viewer_user_id: str) -> str:
    viewer_player_id, opponent_player_id = await _viewer_and_opponent_players(game_id, viewer_user_id)
    if powerup_id == "skip-turn":
        applied = await apply_offensive_modifier(
            game_id,
            target_player_id=opponent_player_id,
            source_player_id=viewer_player_id,
            modifier_type="skip_turn",
        )
        return "Opponent will lose their next turn" if applied else "Opponent's shield blocked the skip"
    await add_modifier(game_id, target_player_id=viewer_player_id, source_player_id=viewer_player_id, modifier_type="extra_turn")
    return "You'll keep your turn after the next guess"


async def _apply_defensive_self_modifier(powerup_id: str, game_id: str, viewer_user_id: str) -> str:
    viewer_player_id, _ = await _viewer_and_opponent_players(game_id, viewer_user_id)
    if powerup_id == "shield":
        await add_modifier(game_id, target_player_id=viewer_player_id, source_player_id=viewer_player_id, modifier_type="shield")
        return "Shield armed - blocks the next offensive power-up"
    if powerup_id == "ghost-guess":
        await add_modifier(game_id, target_player_id=viewer_player_id, source_player_id=viewer_player_id, modifier_type="ghost_guess")
        return "Your next guess will appear as ??? to opponent"
    return "Activated"


async def _apply_offensive_perception(powerup_id: str, game_id: str, viewer_user_id: str) -> str:
    viewer_player_id, opponent_player_id = await _viewer_and_opponent_players(game_id, viewer_user_id)
    modifier_label = {
        "fake-feedback": ("fake_feedback", "Opponent will see fake feedback on their next guess", "Opponent's shield blocked fake feedback"),
        "fog": ("fog", "Opponent's view of their last 2 guesses is now fogged", "Opponent's shield blocked the fog"),
    }[powerup_id]
    modifier_type, on_success, on_blocked = modifier_label
    applied = await apply_offensive_modifier(
        game_id,
        target_player_id=opponent_player_id,
        source_player_id=viewer_player_id,
        modifier_type=modifier_type,  # type: ignore[arg-type]
    )
    return on_success if applied else on_blocked


async def _emit_cosmetic_event(powerup_id: str, game_id: str, viewer_user_id: str) -> str:
    viewer_player_id, opponent_player_id = await _viewer_and_opponent_players(game_id, viewer_user_id)
    target_id = viewer_player_id if powerup_id == "mirror" else opponent_player_id
    await db.match_events.insert_one(
        {
            "game_id": game_id,
            "event": "cosmetic",
            "payload": {"effect": powerup_id, "source_player_id": viewer_player_id, "target_player_id": target_id},
            "created_at": int(time.time()),
        }
    )
    labels = {
        "static-screen": "Opponent's tray will shuffle on their next turn",
        "taunt": "Taunt sent",
        "mirror": "You'll see opponent's next guess result",
        "time-drain": "Opponent's clock drained",
    }
    return labels.get(powerup_id, "Activated")


async def _apply_undo(game_id: str, viewer_user_id: str) -> str:
    viewer_player_id, _ = await _viewer_and_opponent_players(game_id, viewer_user_id)
    last = await db.matchs.find_one(
        {"game_id": game_id, "player_id": viewer_player_id},
        sort=[("date_created", -1)],
    )
    if last is None:
        raise HTTPException(status_code=404, detail="No guess to undo")
    await db.matchs.delete_one({"_id": last["_id"]})
    await db.match_events.insert_one(
        {
            "game_id": game_id,
            "event": "undo",
            "payload": {"player_id": viewer_player_id, "guess": last.get("guess", "")},
            "created_at": int(time.time()),
        }
    )
    return "Last guess removed"


async def use_powerup(game_id: str, viewer_user_id: str, powerup_id: str) -> PowerUpUseResponse:
    inventory = await db.inventory.find_one({"user_id": viewer_user_id})
    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    items = list(inventory["items"])
    reveal: PowerUpReveal | None = None
    effect = "Activated"
    remaining = 0
    for index, item in enumerate(items):
        if item["id"] != powerup_id:
            continue
        if int(item["count"]) <= 0:
            raise HTTPException(status_code=409, detail="Power-up not available")
        if powerup_id in {"peek-in", "peek-out", "pin", "lock-in"}:
            reveal, effect = await _build_reveal(powerup_id, game_id, viewer_user_id)
        elif powerup_id in {"skip-turn", "extra-turn"}:
            effect = await _apply_turn_modifier(powerup_id, game_id, viewer_user_id)
        elif powerup_id == "undo":
            effect = await _apply_undo(game_id, viewer_user_id)
        elif powerup_id in {"shield", "ghost-guess"}:
            effect = await _apply_defensive_self_modifier(powerup_id, game_id, viewer_user_id)
        elif powerup_id in {"fake-feedback", "fog"}:
            effect = await _apply_offensive_perception(powerup_id, game_id, viewer_user_id)
        elif powerup_id in {"static-screen", "taunt", "mirror", "time-drain"}:
            effect = await _emit_cosmetic_event(powerup_id, game_id, viewer_user_id)
        else:
            effect = f"{item['name']} activated"
        items[index] = {**item, "count": int(item["count"]) - 1}
        remaining = int(items[index]["count"])
        break
    else:
        raise HTTPException(status_code=404, detail="Power-up not found")

    await db.inventory.find_one_and_update({"_id": inventory["_id"]}, {"$set": {"items": items, "updated_at": int(time.time())}})
    await db.match_events.insert_one(
        {
            "game_id": game_id,
            "event": "powerup",
            "payload": {"powerup_id": powerup_id, "effect": effect, "user_id": viewer_user_id},
            "created_at": int(time.time()),
        }
    )
    return PowerUpUseResponse(powerup_id=powerup_id, effect=effect, remaining=remaining, reveal=reveal)


async def build_stream_payload(game_id: str, session: MatchSessionResponse | None = None) -> str:
    if session is None:
        session = await build_match_session(game_id, None)
    payload = {
        "type": "state",
        "session": session.model_dump(),
        "generatedAt": int(time.time()),
    }
    return f"data: {json.dumps(payload)}\n\n"
