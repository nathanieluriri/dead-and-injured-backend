from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from schemas.app_features import (
    ChallengeResponse,
    CurriculumPageResponse,
    LessonContent,
    LoadoutSaveRequest,
    NotificationsResponse,
    PracticeGuessRequest,
    PracticeGuessResponse,
    PracticeSessionCreate,
    PracticeSessionOut,
    ProfilePageResponse,
    PuzzleAttemptRequest,
    PuzzleAttemptResponse,
    PuzzleEntry,
    PuzzlesPageResponse,
    SearchResponse,
    SocialPageResponse,
    WalletResponse,
)
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from security.auth import maybe_verify_token, verify_token
from services.app_features_service import (
    attempt_puzzle,
    build_curriculum_page,
    build_profile_page,
    build_puzzles_page,
    build_social_page,
    complete_lesson,
    create_friend_challenge,
    create_practice_session,
    get_daily_puzzle,
    get_inventory,
    get_lesson,
    get_user_achievements,
    get_wallet,
    guess_practice_session,
    list_notifications,
    mark_notification_read,
    remove_friend,
    respond_to_friend_request,
    save_loadout,
    search_catalog,
    send_friend_request,
    set_presence,
)

router = APIRouter(tags=["App Features"])


@router.get("/users/me/profile", response_model=APIResponse[ProfilePageResponse])
async def get_my_profile(token: accessTokenOut = Depends(verify_token)) -> APIResponse[ProfilePageResponse]:
    return ok_response(data=await build_profile_page(token.userId), message="Profile fetched successfully")


@router.get("/users/me/stats", response_model=APIResponse[list[dict[str, str]]])
async def get_my_stats(token: accessTokenOut = Depends(verify_token)) -> APIResponse[list[dict[str, str]]]:
    profile = await build_profile_page(token.userId)
    return ok_response(data=[item.model_dump() for item in profile.stats], message="Stats fetched successfully")


@router.get("/users/me/matches", response_model=APIResponse[list[dict[str, str]]])
async def get_my_match_history(token: accessTokenOut = Depends(verify_token)) -> APIResponse[list[dict[str, str]]]:
    profile = await build_profile_page(token.userId)
    return ok_response(data=[item.model_dump() for item in profile.recentMatches], message="Recent matches fetched successfully")


@router.get("/users/me/achievements", response_model=APIResponse[list[dict[str, str | bool]]])
async def get_my_achievements(token: accessTokenOut = Depends(verify_token)) -> APIResponse[list[dict[str, str | bool]]]:
    achievements = await get_user_achievements(token.userId)
    return ok_response(data=[item.model_dump() for item in achievements], message="Achievements fetched successfully")


@router.get("/users/me/inventory", response_model=APIResponse[list[dict[str, str | int]]])
async def get_my_inventory(token: accessTokenOut = Depends(verify_token)) -> APIResponse[list[dict[str, str | int]]]:
    inventory = await get_inventory(token.userId)
    return ok_response(data=[item.model_dump() for item in inventory], message="Inventory fetched successfully")


@router.post("/users/me/loadout", response_model=APIResponse[dict[str, list[str]]])
async def post_my_loadout(payload: LoadoutSaveRequest, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, list[str]]]:
    return ok_response(data=await save_loadout(token.userId, payload.slots), message="Loadout saved successfully")


@router.get("/wallet/me", response_model=APIResponse[WalletResponse])
async def get_my_wallet(token: accessTokenOut = Depends(verify_token)) -> APIResponse[WalletResponse]:
    return ok_response(data=await get_wallet(token.userId), message="Wallet fetched successfully")


@router.get("/notifications", response_model=APIResponse[NotificationsResponse])
async def get_notifications(token: accessTokenOut = Depends(verify_token)) -> APIResponse[NotificationsResponse]:
    return ok_response(data=await list_notifications(token.userId), message="Notifications fetched successfully")


@router.post("/notifications/{notification_id}/read", response_model=APIResponse[dict[str, str]])
async def post_notification_read(notification_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await mark_notification_read(token.userId, notification_id), message="Notification updated successfully")


@router.get("/search", response_model=APIResponse[SearchResponse])
async def get_search_results(q: str = Query("", min_length=0, max_length=64)) -> APIResponse[SearchResponse]:
    return ok_response(data=await search_catalog(q), message="Search results fetched successfully")


@router.get("/friends", response_model=APIResponse[SocialPageResponse])
async def get_friends(token: accessTokenOut = Depends(verify_token)) -> APIResponse[SocialPageResponse]:
    return ok_response(data=await build_social_page(token.userId), message="Social data fetched successfully")


@router.post("/friends/request", response_model=APIResponse[dict[str, str]])
async def post_friend_request(username: str = Query(...), token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await send_friend_request(token.userId, username), message="Friend request sent successfully")


@router.post("/friends/request/{request_id}/accept", response_model=APIResponse[dict[str, str]])
async def accept_friend_request(request_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await respond_to_friend_request(token.userId, request_id, True), message="Friend request accepted")


@router.post("/friends/request/{request_id}/reject", response_model=APIResponse[dict[str, str]])
async def reject_friend_request(request_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await respond_to_friend_request(token.userId, request_id, False), message="Friend request rejected")


@router.delete("/friends/{friend_id}", response_model=APIResponse[dict[str, str]])
async def delete_friend(friend_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await remove_friend(token.userId, friend_id), message="Friend removed successfully")


@router.post("/friends/{friend_id}/challenge", response_model=APIResponse[ChallengeResponse])
async def challenge_friend(friend_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[ChallengeResponse]:
    return ok_response(data=await create_friend_challenge(token.userId, friend_id), message="Challenge created successfully")


@router.post("/friends/presence", response_model=APIResponse[dict[str, str]])
async def heartbeat_presence(
    status: str = Query("Online", min_length=2, max_length=64),
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[dict[str, str]]:
    return ok_response(data=await set_presence(token.userId, status=status), message="Presence updated")


@router.get("/puzzles/daily", response_model=APIResponse[PuzzleEntry])
async def get_puzzle_daily() -> APIResponse[PuzzleEntry]:
    return ok_response(data=await get_daily_puzzle(), message="Daily puzzle fetched successfully")


@router.get("/puzzles", response_model=APIResponse[PuzzlesPageResponse])
async def get_puzzles(token: accessTokenOut | None = Depends(maybe_verify_token)) -> APIResponse[PuzzlesPageResponse]:
    return ok_response(data=await build_puzzles_page(token.userId if token else None), message="Puzzles fetched successfully")


@router.post("/puzzles/{puzzle_id}/attempt", response_model=APIResponse[PuzzleAttemptResponse])
async def post_puzzle_attempt(
    puzzle_id: str,
    payload: PuzzleAttemptRequest,
    token: accessTokenOut | None = Depends(maybe_verify_token),
) -> APIResponse[PuzzleAttemptResponse]:
    return ok_response(data=await attempt_puzzle(token.userId if token else None, puzzle_id, payload.guess), message="Puzzle attempt recorded")


@router.get("/puzzles/me/progress", response_model=APIResponse[PuzzlesPageResponse])
async def get_puzzle_progress(token: accessTokenOut = Depends(verify_token)) -> APIResponse[PuzzlesPageResponse]:
    return ok_response(data=await build_puzzles_page(token.userId), message="Puzzle progress fetched successfully")


@router.get("/curriculum", response_model=APIResponse[CurriculumPageResponse])
async def get_curriculum(token: accessTokenOut | None = Depends(maybe_verify_token)) -> APIResponse[CurriculumPageResponse]:
    return ok_response(data=await build_curriculum_page(token.userId if token else None), message="Curriculum fetched successfully")


@router.get("/curriculum/{chapter_id}/lessons/{lesson_id}", response_model=APIResponse[LessonContent])
async def get_curriculum_lesson(chapter_id: str, lesson_id: str) -> APIResponse[LessonContent]:
    return ok_response(data=await get_lesson(chapter_id, lesson_id), message="Lesson fetched successfully")


@router.post("/curriculum/{chapter_id}/lessons/{lesson_id}/complete", response_model=APIResponse[dict[str, str]])
async def post_complete_lesson(chapter_id: str, lesson_id: str, token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await complete_lesson(token.userId, chapter_id, lesson_id), message="Lesson completed successfully")


@router.post("/practice/session", response_model=APIResponse[PracticeSessionOut])
async def post_practice_session(payload: PracticeSessionCreate, token: accessTokenOut | None = Depends(maybe_verify_token)) -> APIResponse[PracticeSessionOut]:
    return ok_response(data=await create_practice_session(token.userId if token else None, payload), message="Practice session created successfully")


@router.post("/practice/session/{session_id}/guess", response_model=APIResponse[PracticeGuessResponse])
async def post_practice_guess(
    session_id: str,
    payload: PracticeGuessRequest,
    token: accessTokenOut | None = Depends(maybe_verify_token),
) -> APIResponse[PracticeGuessResponse]:
    return ok_response(data=await guess_practice_session(token.userId if token else None, session_id, payload.guess), message="Practice guess recorded successfully")
