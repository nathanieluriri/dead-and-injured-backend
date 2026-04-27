from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Iterable

from bson import ObjectId
from fastapi import HTTPException

from core.database import db
from repositories.game import create_game, get_game
from repositories.leaderboard import get_leaderboard, get_leaderboards
from repositories.match import get_matchs
from repositories.player import create_player, get_player, get_players
from repositories.scores import get_scores_for_players
from repositories.secret import create_secret
from repositories.user import get_user
from schemas.app_features import (
    AchievementItem,
    ChallengeResponse,
    CurriculumPageResponse,
    FriendItem,
    LeaderboardEntryOut,
    LessonContent,
    LearnChapterItem,
    MatchHistoryItem,
    NotificationItem,
    NotificationsResponse,
    PowerUpItem,
    PracticeGuessResponse,
    PracticeSessionCreate,
    PracticeSessionOut,
    ProfilePageResponse,
    ProfileSummary,
    PuzzleAttemptResponse,
    PuzzleEntry,
    PuzzlesPageResponse,
    PuzzleStats,
    SearchHit,
    SearchResponse,
    SocialPageResponse,
    StatItem,
    WalletResponse,
)
from schemas.game import GameCreate, GameSettings, GameStatus, GameType
from schemas.imports import Player, SecretStr
from schemas.player import PlayerBase, PlayerCreate, PlayerType
from schemas.secret import SecretBase, SecretCreate

DEFAULT_POWERUPS: list[dict[str, str | int]] = [
    {"id": "static-screen", "name": "Static Screen", "description": "Opponent's tray shuffles for their next turn.", "rarity": "common", "category": "offensive", "count": 3},
    {"id": "time-drain", "name": "Time Drain", "description": "Shave 10s off opponent's current turn.", "rarity": "common", "category": "offensive", "count": 5},
    {"id": "skip-turn", "name": "Skip Turn", "description": "Opponent loses their next turn.", "rarity": "rare", "category": "offensive", "count": 1},
    {"id": "fog", "name": "Fog", "description": "Opponent's last 2 guesses blur for 1 turn.", "rarity": "uncommon", "category": "offensive", "count": 2},
    {"id": "mirror", "name": "Mirror", "description": "See opponent's next Dead/Injured count.", "rarity": "rare", "category": "offensive", "count": 1},
    {"id": "peek-in", "name": "Peek - One In", "description": "Reveals one digit in the secret.", "rarity": "uncommon", "category": "defensive", "count": 2},
    {"id": "peek-out", "name": "Peek - One Out", "description": "Reveals one digit not in the secret.", "rarity": "common", "category": "defensive", "count": 4},
    {"id": "pin", "name": "Pin", "description": "Reveals position of one digit.", "rarity": "rare", "category": "defensive", "count": 1},
    {"id": "lock-in", "name": "Lock-In", "description": "Reveals one full digit + position pair.", "rarity": "epic", "category": "defensive", "count": 0},
    {"id": "extra-turn", "name": "Extra Turn", "description": "Take two guesses this turn.", "rarity": "uncommon", "category": "defensive", "count": 2},
    {"id": "undo", "name": "Undo", "description": "Remove your last guess from the board.", "rarity": "rare", "category": "defensive", "count": 1},
    {"id": "shield", "name": "Shield", "description": "Block the next offensive power-up.", "rarity": "uncommon", "category": "defensive", "count": 2},
    {"id": "taunt", "name": "Taunt Emote", "description": "Send a cosmetic emote to opponent.", "rarity": "common", "category": "meta", "count": 8},
    {"id": "fake-feedback", "name": "Fake Feedback", "description": "Bluff opponent with a fake count for 3s.", "rarity": "rare", "category": "meta", "count": 1},
    {"id": "ghost-guess", "name": "Ghost Guess", "description": "Submit a guess opponent sees as ???.", "rarity": "uncommon", "category": "meta", "count": 2},
]

DEFAULT_CURRICULUM = [
    {"id": "chapter-1", "title": "How Dead & Injured works", "lessons": 4, "body": "Understand dead and injured counts and how each guess narrows the search space."},
    {"id": "chapter-2", "title": "Using the digit tray", "lessons": 5, "body": "Track available, eliminated, and locked digits efficiently while guessing."},
    {"id": "chapter-3", "title": "Beginner strategies", "lessons": 6, "body": "Open with information-rich guesses and avoid wasteful overlap too early."},
    {"id": "chapter-4", "title": "Deduction techniques", "lessons": 8, "body": "Use constraint elimination to reduce the candidate set after each round."},
]

DEFAULT_PUZZLES = [
    {"id": "daily", "icon": "calendar", "title": "Daily Puzzle", "diff": "Silver", "time": "~3 min", "href": "/puzzles/daily", "secret": "8163"},
    {"id": "puzzle-284", "icon": "target", "title": "Find the Number #284", "diff": "Gold", "time": "~5 min", "href": "/puzzles/puzzle-284", "secret": "5291"},
    {"id": "logic-cascade", "icon": "brain", "title": "Logic Cascade", "diff": "Diamond", "time": "~12 min", "href": "/puzzles/logic-cascade", "secret": "4072"},
]

DEFAULT_NOTIFICATIONS = [
    {"kind": "system", "title": "Welcome to Dead & Injured", "body": "Start a bot or local match to warm up your deduction game."},
]


def _rank_label(rank: int | None) -> str:
    if rank is None:
        return "Unranked"
    return f"Rank #{rank}"


def _initials(username: str) -> str:
    parts = [part for part in username.replace(".", " ").replace("_", " ").split(" ") if part]
    if not parts:
        return "NA"
    return "".join(part[0].upper() for part in parts[:2])


def _practice_hint(secret: str) -> str:
    return f"Try anchoring digit {secret[0]} in a new position."


async def _get_safe_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    user = await get_user({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _ensure_inventory(user_id: str) -> list[dict]:
    inventory = await db.inventory.find_one({"user_id": user_id})
    if inventory is None:
        inventory = {"user_id": user_id, "items": DEFAULT_POWERUPS, "updated_at": int(time.time())}
        await db.inventory.insert_one(inventory)
    return list(inventory["items"])


async def _ensure_wallet(user_id: str) -> dict:
    wallet = await db.wallets.find_one({"user_id": user_id})
    if wallet is None:
        wallet = {"user_id": user_id, "balance": 1284, "currency": "coins", "updated_at": int(time.time())}
        await db.wallets.insert_one(wallet)
    return wallet


async def _ensure_notifications(user_id: str) -> list[dict]:
    cursor = db.notifications.find({"user_id": user_id}).sort("created_at", -1)
    items = [doc async for doc in cursor]
    if items:
        return items

    now = int(time.time())
    seeded = [
        {
            "user_id": user_id,
            "kind": item["kind"],
            "title": item["title"],
            "body": item["body"],
            "unread": True,
            "created_at": now,
        }
        for item in DEFAULT_NOTIFICATIONS
    ]
    if seeded:
        await db.notifications.insert_many(seeded)
    return seeded


async def _create_notification(
    user_id: str,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, str] | None = None,
) -> None:
    document: dict = {
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body,
        "unread": True,
        "created_at": int(time.time()),
    }
    if payload:
        document["payload"] = payload
    await db.notifications.insert_one(document)


async def _ensure_curriculum() -> list[dict]:
    existing = await db.curriculum.find_one({"seeded": True})
    if existing is None:
        await db.curriculum.insert_one({"seeded": True, "chapters": DEFAULT_CURRICULUM})
        return DEFAULT_CURRICULUM
    return list(existing["chapters"])


async def _ensure_puzzles() -> list[dict]:
    cursor = db.puzzles.find({})
    puzzles = [doc async for doc in cursor]
    if puzzles:
        return puzzles
    docs = [{**puzzle, "seeded": True} for puzzle in DEFAULT_PUZZLES]
    await db.puzzles.insert_many(docs)
    return docs


def _to_powerups(items: Iterable[dict]) -> list[PowerUpItem]:
    return [PowerUpItem(**item) for item in items]


async def build_profile_page(user_id: str) -> ProfilePageResponse:
    user = await _get_safe_user(user_id)
    players = await get_players(filter_dict={"user_id": user_id}, start=0, stop=500)
    player_ids = [player.id for player in players if player.id]
    scores = await get_scores_for_players(player_ids)
    wins = sum(1 for score in scores if int(score.match_result) == 1)
    losses = sum(1 for score in scores if int(score.match_result) == 0)
    total = wins + losses
    inventory = _to_powerups(await _ensure_inventory(user_id))
    wallet = await _ensure_wallet(user_id)

    leaderboard_entry = await get_leaderboard({"user_id": user_id})
    recent_matches: list[MatchHistoryItem] = []
    seen_match_ids: set[str] = set()
    for player in players:
        matches = await get_matchs(filter_dict={"player_id": player.id}, start=0, stop=10)
        for match in matches:
            if not match.id or match.id in seen_match_ids:
                continue
            seen_match_ids.add(match.id)
            game = await get_game({"_id": ObjectId(match.game_id)})
            if game is None:
                continue
            opponent_player_id = game.joiner_player_id if game.creator_player_id == player.id else game.creator_player_id
            opponent_player = await get_player({"_id": ObjectId(opponent_player_id)}) if opponent_player_id and ObjectId.is_valid(opponent_player_id) else None
            opponent_name = "Bot"
            if opponent_player is not None:
                if opponent_player.user_id == "bot":
                    opponent_name = "Bot"
                elif ObjectId.is_valid(opponent_player.user_id):
                    opponent_user = await get_user({"_id": ObjectId(opponent_player.user_id)})
                    if opponent_user is not None:
                        opponent_name = opponent_user.username
            result = "win" if match.dead == len(match.guess) else "loss"
            mode = "Ranked" if game.settings.is_public else "Private"
            recent_matches.append(
                MatchHistoryItem(
                    matchId=match.id,
                    opp=opponent_name,
                    mode=mode,
                    result=result,
                    change="+1 win" if result == "win" else "0 wins",
                )
            )
    recent_matches = recent_matches[:4]

    summary = ProfileSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        initials=_initials(user.username),
        wins=wins,
        rankLabel=_rank_label(leaderboard_entry.rank if leaderboard_entry else None),
        joinedLabel=f"Joined {datetime.fromtimestamp(user.date_created, tz=timezone.utc):%b %Y}" if user.date_created else "Joined recently",
        bio=user.bio,
        avatar_url=user.avatar_url,
    )
    stats = [
        StatItem(label="Rating", value=str(wins)),
        StatItem(label="Matches", value=str(total)),
        StatItem(label="Wins", value=str(wins)),
        StatItem(label="Losses", value=str(losses)),
        StatItem(label="Win Rate", value=f"{round((wins / total) * 100) if total else 0}%"),
        StatItem(label="Coins", value=str(wallet["balance"])),
        StatItem(label="Current Streak", value=f"{max(wins - losses, 0)}d"),
    ]
    return ProfilePageResponse(user=summary, stats=stats, recentMatches=recent_matches, inventory=inventory)


async def build_social_page(user_id: str) -> SocialPageResponse:
    friendships_cursor = db.friendships.find({"users": user_id})
    friends: list[FriendItem] = []
    async for doc in friendships_cursor:
        other_user_id = next(candidate for candidate in doc["users"] if candidate != user_id)
        other_user = await _get_safe_user(other_user_id)
        presence = await db.presence.find_one({"user_id": other_user_id})
        is_online = bool(presence and presence.get("last_seen", 0) > int(time.time()) - 120)
        status = "Online" if is_online else "Last seen recently"
        if presence and presence.get("status"):
            status = str(presence["status"])
        friends.append(FriendItem(id=other_user.id, name=other_user.username, status=status, online=is_online))

    leaders = await get_leaderboards(start=0, stop=5)
    leader_items: list[LeaderboardEntryOut] = []
    for entry in leaders:
        leader_user = await get_user({"_id": ObjectId(entry.user_id)}) if ObjectId.is_valid(entry.user_id) else None
        leader_items.append(
            LeaderboardEntryOut(
                rank=entry.rank,
                name=leader_user.username if leader_user else entry.email.split("@")[0],
                wins=entry.wins,
            )
        )
    return SocialPageResponse(friends=friends, leaders=leader_items)


async def send_friend_request(user_id: str, username: str) -> dict[str, str]:
    target = await get_user({"username": username})
    if target is None:
        raise HTTPException(status_code=404, detail="Target user not found")
    if target.id == user_id:
        raise HTTPException(status_code=409, detail="Cannot friend yourself")
    existing = await db.friend_requests.find_one({"from_user_id": user_id, "to_user_id": target.id, "status": "pending"})
    if existing is not None:
        raise HTTPException(status_code=409, detail="Friend request already pending")
    result = await db.friend_requests.insert_one(
        {"from_user_id": user_id, "to_user_id": target.id, "status": "pending", "created_at": int(time.time())}
    )
    await _create_notification(target.id, "friend_request", "New friend request", f"{username} sent you a friend request.")
    return {"status": "pending", "request_id": str(result.inserted_id), "target_user_id": target.id}


async def respond_to_friend_request(user_id: str, request_id: str, accept: bool) -> dict[str, str]:
    if not ObjectId.is_valid(request_id):
        raise HTTPException(status_code=400, detail="Invalid request id")
    request_doc = await db.friend_requests.find_one({"_id": ObjectId(request_id), "to_user_id": user_id, "status": "pending"})
    if request_doc is None:
        raise HTTPException(status_code=404, detail="Friend request not found")
    new_status = "accepted" if accept else "rejected"
    await db.friend_requests.find_one_and_update({"_id": request_doc["_id"]}, {"$set": {"status": new_status}})
    if accept:
        await db.friendships.insert_one({"users": [request_doc["from_user_id"], user_id], "created_at": int(time.time())})
        await _create_notification(request_doc["from_user_id"], "friend_accept", "Friend request accepted", "Your friend request was accepted.")
    return {"status": new_status}


async def remove_friend(user_id: str, friend_id: str) -> dict[str, str]:
    result = await db.friendships.delete_one({"users": {"$all": [user_id, friend_id]}})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Friendship not found")
    return {"status": "removed"}


async def create_friend_challenge(user_id: str, friend_id: str) -> ChallengeResponse:
    game = await create_game(
        GameCreate(
            settings=GameSettings(is_timed=False, how_many_minutes=0, is_public=False, game_type=GameType.multiplayer),
            status=GameStatus.waiting,
            creator_player_id=user_id,
        )
    )
    creator = await create_player(PlayerCreate(**PlayerBase(user_id=user_id, game_id=game.id, player_type=PlayerType.creator).model_dump()))
    friend = await create_player(PlayerCreate(**PlayerBase(user_id=friend_id, game_id=game.id, player_type=PlayerType.joiner).model_dump()))
    await db.games.find_one_and_update(
        {"_id": ObjectId(game.id)},
        {"$set": {"creator_player_id": creator.id, "joiner_player_id": friend.id, "mode": "friend"}},
    )
    challenger = await _get_safe_user(user_id)
    await _create_notification(
        friend_id,
        "challenge",
        "New challenge",
        f"{challenger.username} challenged you to a private match.",
        payload={"match_id": game.id} if game.id else None,
    )
    return ChallengeResponse(game_id=game.id, challenged_user_id=friend_id, status="waiting")


async def save_loadout(user_id: str, slots: list[str]) -> dict[str, list[str]]:
    await _ensure_inventory(user_id)
    await db.loadouts.find_one_and_update(
        {"user_id": user_id},
        {"$set": {"slots": slots[:5], "updated_at": int(time.time())}},
        upsert=True,
    )
    return {"slots": slots[:5]}


async def get_inventory(user_id: str) -> list[PowerUpItem]:
    return _to_powerups(await _ensure_inventory(user_id))


async def get_wallet(user_id: str) -> WalletResponse:
    wallet = await _ensure_wallet(user_id)
    return WalletResponse(balance=int(wallet["balance"]), currency=str(wallet.get("currency", "coins")))


async def list_notifications(user_id: str) -> NotificationsResponse:
    items = await _ensure_notifications(user_id)
    normalized = [
        NotificationItem(
            id=str(item.get("_id", item.get("id", ""))),
            kind=str(item["kind"]),
            title=str(item["title"]),
            body=str(item["body"]),
            unread=bool(item.get("unread", True)),
            createdAt=int(item.get("created_at", int(time.time()))),
            payload={k: str(v) for k, v in item["payload"].items()} if isinstance(item.get("payload"), dict) else None,
        )
        for item in items
    ]
    unread_count = sum(1 for item in normalized if item.unread)
    return NotificationsResponse(unreadCount=unread_count, items=normalized)


async def mark_notification_read(user_id: str, notification_id: str) -> dict[str, str]:
    if not ObjectId.is_valid(notification_id):
        raise HTTPException(status_code=400, detail="Invalid notification id")
    result = await db.notifications.find_one_and_update(
        {"_id": ObjectId(notification_id), "user_id": user_id},
        {"$set": {"unread": False}},
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}


async def search_catalog(query: str) -> SearchResponse:
    q = query.strip()
    if not q:
        return SearchResponse(query=query, results=[])

    regex = {"$regex": q, "$options": "i"}
    users_cursor = db.users.find({"username": regex}).limit(5)
    puzzles_cursor = db.puzzles.find({"title": regex}).limit(5)

    results: list[SearchHit] = []
    async for user in users_cursor:
        results.append(
            SearchHit(
                id=str(user["_id"]),
                kind="player",
                label=str(user["username"]),
                subtitle="Player",
                href="/social",
            )
        )
    async for puzzle in puzzles_cursor:
        results.append(
            SearchHit(
                id=str(puzzle["id"]),
                kind="puzzle",
                label=str(puzzle["title"]),
                subtitle=str(puzzle["diff"]),
                href=f"/puzzles/{puzzle['id']}",
            )
        )
    return SearchResponse(query=query, results=results)


async def build_puzzles_page(user_id: str | None) -> PuzzlesPageResponse:
    puzzles = await _ensure_puzzles()
    solved_count = 0
    if user_id:
        solved_count = await db.puzzle_attempts.count_documents({"user_id": user_id, "solved": True})
    entries = []
    for puzzle in puzzles:
        solved = False
        if user_id:
            solved = await db.puzzle_attempts.find_one({"user_id": user_id, "puzzle_id": puzzle["id"], "solved": True}) is not None
        entries.append(
            PuzzleEntry(
                id=puzzle["id"],
                icon=puzzle["icon"],
                title=puzzle["title"],
                diff=puzzle["diff"],
                time=puzzle["time"],
                solved=solved,
                href=puzzle["href"],
            )
        )
    stats = PuzzleStats(wins=solved_count, streak=f"{solved_count}d", weeklySolved=solved_count, weeklyTarget=21, weeklyProgress=min(100, int((solved_count / 21) * 100) if solved_count else 0))
    return PuzzlesPageResponse(stats=stats, puzzles=entries)


async def get_daily_puzzle() -> PuzzleEntry:
    puzzles = await _ensure_puzzles()
    day_index = datetime.now(timezone.utc).toordinal() % len(puzzles)
    puzzle = puzzles[day_index]
    return PuzzleEntry(id=puzzle["id"], icon=puzzle["icon"], title=puzzle["title"], diff=puzzle["diff"], time=puzzle["time"], solved=False, href=puzzle["href"])


async def attempt_puzzle(user_id: str | None, puzzle_id: str, guess: str) -> PuzzleAttemptResponse:
    puzzle = await db.puzzles.find_one({"id": puzzle_id})
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    result = Player(code=puzzle["secret"]).guess_result(guess=guess)
    solved = bool(result.game_over)
    if user_id:
        await db.puzzle_attempts.insert_one({"user_id": user_id, "puzzle_id": puzzle_id, "guess": guess, "dead": result.dead, "injured": result.injured, "solved": solved, "created_at": int(time.time())})
        if solved:
            wallet = await _ensure_wallet(user_id)
            await db.wallets.find_one_and_update({"_id": wallet["_id"]}, {"$set": {"balance": int(wallet["balance"]) + 25, "updated_at": int(time.time())}})
            await _create_notification(user_id, "puzzle_solved", "Puzzle solved", f"You solved {puzzle['title']} and earned 25 coins.")
    return PuzzleAttemptResponse(dead=result.dead, injured=result.injured, solved=solved)


async def build_curriculum_page(user_id: str | None) -> CurriculumPageResponse:
    chapters = await _ensure_curriculum()
    completed_ids: set[str] = set()
    if user_id:
        progress_cursor = db.curriculum_progress.find({"user_id": user_id})
        completed_ids = {doc["chapter_id"] async for doc in progress_cursor}
    chapter_items: list[LearnChapterItem] = []
    for index, chapter in enumerate(chapters):
        if chapter["id"] in completed_ids:
            status = "done"
        elif index == 0 or chapters[index - 1]["id"] in completed_ids or not user_id:
            status = "current"
        else:
            status = "locked"
        chapter_items.append(LearnChapterItem(id=chapter["id"], title=chapter["title"], lessons=chapter["lessons"], status=status, href=f"/learn/{chapter['id']}/lesson-1"))
    return CurriculumPageResponse(chapters=chapter_items)


async def get_lesson(chapter_id: str, lesson_id: str) -> LessonContent:
    chapters = await _ensure_curriculum()
    chapter = next((item for item in chapters if item["id"] == chapter_id), None)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return LessonContent(chapter_id=chapter_id, lesson_id=lesson_id, title=chapter["title"], body=chapter["body"])


async def complete_lesson(user_id: str, chapter_id: str, lesson_id: str) -> dict[str, str]:
    await db.curriculum_progress.find_one_and_update(
        {"user_id": user_id, "chapter_id": chapter_id, "lesson_id": lesson_id},
        {"$set": {"completed_at": int(time.time())}},
        upsert=True,
    )
    return {"status": "completed"}


def _generate_secret(length: int, allow_duplicates: bool) -> str:
    digits: list[str] = []
    while len(digits) < length:
        digit = str(random.randint(0, 9))
        if not allow_duplicates and digit in digits:
            continue
        digits.append(digit)
    return "".join(digits)


async def create_practice_session(user_id: str | None, payload: PracticeSessionCreate) -> PracticeSessionOut:
    secret = _generate_secret(payload.length, payload.allow_duplicates)
    session_id = str(ObjectId())
    await db.practice_sessions.insert_one(
        {
            "_id": ObjectId(session_id),
            "user_id": user_id,
            "secret": secret,
            "length": payload.length,
            "allow_duplicates": payload.allow_duplicates,
            "unlimited_attempts": payload.unlimited_attempts,
            "hints_enabled": payload.hints_enabled,
            "powerup_test": payload.powerup_test,
            "attempts": 0,
            "created_at": int(time.time()),
        }
    )
    return PracticeSessionOut(session_id=session_id, length=payload.length, unlimited_attempts=payload.unlimited_attempts, hints_enabled=payload.hints_enabled, powerup_test=payload.powerup_test)


async def guess_practice_session(user_id: str | None, session_id: str, guess: str) -> PracticeGuessResponse:
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid practice session id")
    session = await db.practice_sessions.find_one({"_id": ObjectId(session_id), "user_id": user_id})
    if session is None:
        raise HTTPException(status_code=404, detail="Practice session not found")
    result = Player(code=session["secret"]).guess_result(guess=guess)
    attempts = int(session.get("attempts", 0)) + 1
    await db.practice_sessions.find_one_and_update({"_id": session["_id"]}, {"$set": {"attempts": attempts}})
    hint = None
    if session.get("hints_enabled") and not result.game_over:
        hint = _practice_hint(session["secret"])
    return PracticeGuessResponse(dead=result.dead, injured=result.injured, solved=result.game_over, hint=hint)


async def get_user_achievements(user_id: str) -> list[AchievementItem]:
    profile = await build_profile_page(user_id)
    total_matches = int(next(item.value for item in profile.stats if item.label == "Matches"))
    return [
        AchievementItem(id="first-blood", name="First Blood", description="Win your first match.", unlocked=profile.user.wins > 0),
        AchievementItem(id="collector", name="Collector", description="Own at least 10 power-up items.", unlocked=sum(item.count for item in profile.inventory) >= 10),
        AchievementItem(id="grinder", name="Grinder", description="Play at least 10 matches.", unlocked=total_matches >= 10),
    ]


async def set_presence(user_id: str, status: str = "Online") -> dict[str, str]:
    await db.presence.find_one_and_update(
        {"user_id": user_id},
        {"$set": {"last_seen": int(time.time()), "status": status}},
        upsert=True,
    )
    return {"status": "ok"}
