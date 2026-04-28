from __future__ import annotations

import asyncio
import json
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.matchmaking_events import subscribe as subscribe_matchmaking_events
from schemas.app_features import LocalGameCreateRequest, MatchSessionResponse, MatchmakingQueueResponse
from schemas.game import GameOut
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from schemas.validators import CodeStr
from security.auth import maybe_verify_token, verify_token, verify_token_email_verified
from services.game_service import retrieve_available_games
from services.live_game_service import (
    create_local_game,
    create_single_player_game,
    get_active_friend_game,
    get_matchmaking_status,
    join_matchmaking_queue,
    leave_matchmaking_queue,
    submit_join_secret,
)


router = APIRouter(prefix="/games", tags=["Games"])


class JoinSecretPayload(BaseModel):
    secret: CodeStr


@router.get("/{start}/{stop}", response_model=APIResponse[List[GameOut]])
async def list_games(start: int = 0, stop: int = 100) -> APIResponse[List[GameOut]]:
    items = await retrieve_available_games(start, stop)
    return ok_response(data=items, message="Games fetched successfully")


@router.post("/single", response_model=APIResponse[MatchSessionResponse])
async def create_single_player_match(token: accessTokenOut | None = Depends(maybe_verify_token)) -> APIResponse[MatchSessionResponse]:
    session = await create_single_player_game(token.userId if token else None)
    return ok_response(data=session, message="Single-player match created successfully")


@router.post("/local", response_model=APIResponse[MatchSessionResponse])
async def create_local_match(payload: LocalGameCreateRequest) -> APIResponse[MatchSessionResponse]:
    session = await create_local_game(payload)
    return ok_response(data=session, message="Local match created successfully")


@router.post("/join/{game_id}", response_model=APIResponse[MatchSessionResponse], dependencies=[Depends(verify_token)])
async def join_game_with_secret(
    game_id: str,
    payload: JoinSecretPayload,
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[MatchSessionResponse]:
    session = await submit_join_secret(game_id, token.userId, payload.secret)
    return ok_response(data=session, message="Secret submitted successfully")


@router.get("/me/friend", response_model=APIResponse[MatchSessionResponse | None], dependencies=[Depends(verify_token)])
async def get_my_friend_game(token: accessTokenOut = Depends(verify_token)) -> APIResponse[MatchSessionResponse | None]:
    return ok_response(data=await get_active_friend_game(token.userId), message="Friend game fetched successfully")


@router.post(
    "/matchmaking/queue",
    response_model=APIResponse[MatchmakingQueueResponse],
    dependencies=[Depends(verify_token_email_verified)],
)
async def enqueue_matchmaking(
    token: accessTokenOut = Depends(verify_token_email_verified),
) -> APIResponse[MatchmakingQueueResponse]:
    return ok_response(data=await join_matchmaking_queue(token.userId), message="Queue status updated successfully")


@router.delete("/matchmaking/queue", response_model=APIResponse[dict[str, str]], dependencies=[Depends(verify_token)])
async def dequeue_matchmaking(token: accessTokenOut = Depends(verify_token)) -> APIResponse[dict[str, str]]:
    return ok_response(data=await leave_matchmaking_queue(token.userId), message="Queue status updated successfully")


@router.get("/matchmaking/status", response_model=APIResponse[MatchmakingQueueResponse], dependencies=[Depends(verify_token)])
async def queue_status(token: accessTokenOut = Depends(verify_token)) -> APIResponse[MatchmakingQueueResponse]:
    return ok_response(data=await get_matchmaking_status(token.userId), message="Queue status fetched successfully")


@router.get("/matchmaking/stream", dependencies=[Depends(verify_token)])
async def stream_matchmaking(token: accessTokenOut = Depends(verify_token)) -> StreamingResponse:
    user_id = token.userId

    async def event_generator():
        async with subscribe_matchmaking_events(user_id) as queue:
            current = await get_matchmaking_status(user_id)
            yield f"data: {json.dumps({'type': 'snapshot', 'status': current.model_dump()})}\n\n"
            if current.status == "matched":
                return
            for _ in range(120):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "match_found":
                        return
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
