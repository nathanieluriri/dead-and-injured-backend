from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.validators import CodeStr


class ProfileSummary(BaseModel):
    id: str
    username: str
    email: str
    initials: str
    wins: int
    rankLabel: str
    joinedLabel: str
    bio: str | None = None
    avatar_url: str | None = None
    profile_media_url: str | None = None
    profile_media_type: str | None = None
    profile_media_kind: str | None = None
    isEmailVerified: bool = False


class StatItem(BaseModel):
    label: str
    value: str


class MatchHistoryItem(BaseModel):
    matchId: str
    opp: str
    mode: str
    result: Literal["win", "loss"]
    change: str


class AchievementItem(BaseModel):
    id: str
    name: str
    description: str
    unlocked: bool = True


class PowerUpItem(BaseModel):
    id: str
    name: str
    description: str
    rarity: str
    category: str
    count: int


class ProfilePageResponse(BaseModel):
    user: ProfileSummary
    stats: list[StatItem]
    recentMatches: list[MatchHistoryItem]
    inventory: list[PowerUpItem]


class FriendItem(BaseModel):
    id: str
    name: str
    status: str
    online: bool
    profile_media_url: str | None = None
    profile_media_type: str | None = None
    profile_media_kind: str | None = None


class LeaderboardEntryOut(BaseModel):
    rank: int
    name: str
    wins: int
    profile_media_url: str | None = None
    profile_media_type: str | None = None
    profile_media_kind: str | None = None


class SocialPageResponse(BaseModel):
    friends: list[FriendItem]
    leaders: list[LeaderboardEntryOut]


class LoadoutSaveRequest(BaseModel):
    slots: list[str] = Field(default_factory=list, max_length=5)


class ChallengeResponse(BaseModel):
    game_id: str
    challenged_user_id: str
    status: str


class PuzzleStats(BaseModel):
    wins: int
    streak: str
    weeklySolved: int
    weeklyTarget: int
    weeklyProgress: int


class PuzzleEntry(BaseModel):
    id: str
    icon: Literal["calendar", "target", "timer", "brain"]
    title: str
    diff: str
    time: str
    solved: bool
    href: str


class PuzzlesPageResponse(BaseModel):
    stats: PuzzleStats
    puzzles: list[PuzzleEntry]


class PuzzleAttemptRequest(BaseModel):
    guess: str


class PuzzleAttemptResponse(BaseModel):
    dead: int
    injured: int
    solved: bool


class LearnChapterItem(BaseModel):
    id: str
    title: str
    lessons: int
    status: Literal["done", "current", "locked"]
    href: str


class LessonContent(BaseModel):
    chapter_id: str
    lesson_id: str
    title: str
    body: str


class CurriculumPageResponse(BaseModel):
    chapters: list[LearnChapterItem]


class PracticeSessionCreate(BaseModel):
    length: int = Field(4, ge=3, le=8)
    allow_duplicates: bool = False
    unlimited_attempts: bool = True
    hints_enabled: bool = False
    powerup_test: bool = False


class PracticeSessionOut(BaseModel):
    session_id: str
    length: int
    unlimited_attempts: bool
    hints_enabled: bool
    powerup_test: bool


class PracticeGuessRequest(BaseModel):
    guess: CodeStr


class PracticeGuessResponse(BaseModel):
    dead: int
    injured: int
    solved: bool
    hint: str | None = None


class NotificationItem(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    unread: bool = True
    createdAt: int
    payload: dict[str, str] | None = None


class NotificationsResponse(BaseModel):
    unreadCount: int
    items: list[NotificationItem]


class WalletResponse(BaseModel):
    balance: int
    currency: str = "coins"


class SearchHit(BaseModel):
    id: str
    kind: Literal["player", "puzzle"]
    label: str
    subtitle: str
    href: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


class MatchSessionOpponent(BaseModel):
    initials: str
    name: str
    subtitle: str
    profile_media_url: str | None = None
    profile_media_type: str | None = None
    profile_media_kind: str | None = None


class MatchSessionGuess(BaseModel):
    attempt: int
    digits: list[int]
    dead: int
    injured: int
    byViewer: bool


class MatchSessionResponse(BaseModel):
    id: str
    mode: Literal["bot", "online", "friend", "local", "practice", "puzzle"]
    status: str
    canGuess: bool
    viewerPlayerId: str | None = None
    opponent: MatchSessionOpponent
    history: list[MatchSessionGuess]
    loadout: list[PowerUpItem]
    streamUrl: str | None = None
    guessUrl: str | None = None
    powerupUrl: str | None = None
    practiceSessionId: str | None = None


class MatchGuessRequest(BaseModel):
    guess: CodeStr


class MatchGuessResponse(BaseModel):
    attempt: int
    dead: int
    injured: int
    solved: bool
    status: str


class PowerUpUseRequest(BaseModel):
    powerup_id: str


class PowerUpReveal(BaseModel):
    kind: Literal["pin", "lock-in", "peek-in", "peek-out"]
    digit: int | None = None
    position: int | None = None


class PowerUpUseResponse(BaseModel):
    powerup_id: str
    effect: str
    remaining: int
    reveal: PowerUpReveal | None = None


class LocalGameCreateRequest(BaseModel):
    creator_secret: CodeStr
    joiner_secret: CodeStr


class MatchmakingQueueResponse(BaseModel):
    status: Literal["queued", "matched", "idle"]
    match_id: str | None = None
    opponent_name: str | None = None
