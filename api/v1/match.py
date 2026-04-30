import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from core.rate_limit import limiter
from schemas.app_features import MatchGuessRequest, MatchGuessResponse, MatchSessionResponse, PowerUpUseRequest, PowerUpUseResponse
from schemas.match import MatchBase, MatchOut
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from security.auth import maybe_verify_token, verify_token, verify_token_email_verified
from services.live_game_service import build_match_session, build_stream_payload, submit_guess, use_powerup
from services.match_service import add_match, retrieve_match_by_match_id, retrieve_matchs
from services.player_service import retrieve_player_for_user_in_game

router = APIRouter(prefix="/matches", tags=["Matches"])
legacy_router = APIRouter(prefix="/matchs", tags=["Matchs"], include_in_schema=False)


@router.get("/{gameId}/{start}/{stop}", response_model=APIResponse[list[MatchOut]], dependencies=[Depends(verify_token)])
@legacy_router.get("/{gameId}/{start}/{stop}", response_model=APIResponse[list[MatchOut]], dependencies=[Depends(verify_token)])
async def list_matches(
    gameId: str,
    start: int = 0,
    stop: int = 100,
) -> APIResponse[list[MatchOut]]:
    items = await retrieve_matchs(gameId, start, stop)
    return ok_response(data=items, message="Matches fetched successfully")


@router.get("/me", response_model=APIResponse[MatchOut], dependencies=[Depends(verify_token)])
@legacy_router.get("/me", response_model=APIResponse[MatchOut], dependencies=[Depends(verify_token)])
async def get_my_match(
    id: str = Query(..., description="Match ID to fetch"),
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[MatchOut]:
    item = await retrieve_match_by_match_id(id=id)
    player = await retrieve_player_for_user_in_game(user_id=token.userId, game_id=item.game_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Match not found for user")
    return ok_response(data=item, message="Match fetched successfully")


@router.get("/{game_id}/session", response_model=APIResponse[MatchSessionResponse])
async def get_match_session(
    game_id: str,
    token: accessTokenOut | None = Depends(maybe_verify_token),
) -> APIResponse[MatchSessionResponse]:
    session = await build_match_session(game_id, token.userId if token else None)
    return ok_response(data=session, message="Match session fetched successfully")


@router.post("/{game_id}/guess", response_model=APIResponse[MatchGuessResponse])
@limiter.limit("60/minute")
async def post_match_guess(
    request: Request,
    game_id: str,
    payload: MatchGuessRequest,
    viewer_player_id: str | None = Query(None),
    token: accessTokenOut | None = Depends(maybe_verify_token),
) -> APIResponse[MatchGuessResponse]:
    result = await submit_guess(game_id, payload.guess, token.userId if token else None, viewer_player_id=viewer_player_id)
    return ok_response(data=result, message="Guess recorded successfully")


@router.post("/{game_id}/powerup", response_model=APIResponse[PowerUpUseResponse], dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
async def post_match_powerup(
    request: Request,
    game_id: str,
    payload: PowerUpUseRequest,
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[PowerUpUseResponse]:
    result = await use_powerup(game_id, token.userId, payload.powerup_id)
    return ok_response(data=result, message="Power-up used successfully")


@router.get("/{game_id}/stream")
async def stream_match(game_id: str) -> StreamingResponse:
    async def event_generator():
        for _ in range(30):
            session = await build_match_session(game_id, None)
            yield await build_stream_payload(game_id, session=session)
            if session.status in {"completed", "expired"}:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/multiplayer-round", response_model=APIResponse[MatchOut], dependencies=[Depends(verify_token_email_verified)])
@legacy_router.post("/multiplayer-round", response_model=APIResponse[MatchOut], dependencies=[Depends(verify_token_email_verified)])
async def play_match(match_data: MatchBase, token: accessTokenOut = Depends(verify_token_email_verified)) -> APIResponse[MatchOut]:
    player = await retrieve_player_for_user_in_game(user_id=token.userId, game_id=match_data.game_id)
    if player is None or player.id != match_data.player_id:
        raise HTTPException(status_code=403, detail="Match player_id does not belong to the authenticated user")
    item = await add_match(match_data)
    return ok_response(data=item, message="Match recorded successfully")


router.include_router(legacy_router)
