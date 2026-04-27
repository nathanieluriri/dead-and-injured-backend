from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request, Response, status

from core.config import get_settings
from core.cookies import clear_auth_cookies, set_auth_cookies
from core.rate_limit import limiter
from schemas.response_schema import APIResponse, ok_response
from schemas.tokens_schema import accessTokenOut
from schemas.user import (
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserLogin,
    UserOut,
    UserRefresh,
    UserSignup,
    UserUpdate,
)
from security.auth import verify_token, verify_token_to_refresh
from services.user_service import (
    add_user,
    authenticate_user,
    confirm_password_reset,
    logout_user,
    refresh_user_tokens_reduce_number_of_logins,
    remove_user,
    request_password_reset,
    retrieve_user_by_user_id,
    retrieve_users,
    update_user_by_id,
    verify_email,
)

router = APIRouter(prefix="/users", tags=["Users"])
settings = get_settings()


@router.get(
    "/{start}/{stop}",
    response_model=APIResponse[List[UserOut]],
    response_model_exclude_none=True,
    dependencies=[Depends(verify_token)],
)
async def list_users(start: int = 0, stop: int = 100) -> APIResponse[List[UserOut]]:
    items = await retrieve_users(start, stop)
    return ok_response(data=items, message="Users fetched successfully")


@router.get(
    "/me",
    response_model=APIResponse[UserOut],
    dependencies=[Depends(verify_token)],
    response_model_exclude_none=True,
)
async def get_my_user(token: accessTokenOut = Depends(verify_token)) -> APIResponse[UserOut]:
    item = await retrieve_user_by_user_id(id=token.userId)
    return ok_response(data=item, message="User fetched successfully")


@router.patch(
    "/me",
    response_model=APIResponse[UserOut],
    dependencies=[Depends(verify_token)],
    response_model_exclude_none=True,
)
async def patch_my_user(
    user_data: UserUpdate,
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[UserOut]:
    item = await update_user_by_id(user_id=token.userId, user_data=user_data)
    return ok_response(data=item, message="Profile updated successfully")


@router.post("/signup", response_model=APIResponse[UserOut], status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup_new_user(request: Request, user_data: UserSignup, response: Response) -> APIResponse[UserOut]:
    session = await add_user(user_data=user_data)
    set_auth_cookies(response, session.access_token, session.refresh_token)
    return ok_response(data=session.user, message="Account created successfully")


@router.post("/login", response_model=APIResponse[UserOut])
@limiter.limit("10/minute")
async def login_user(request: Request, user_data: UserLogin, response: Response) -> APIResponse[UserOut]:
    session = await authenticate_user(user_data=user_data)
    set_auth_cookies(response, session.access_token, session.refresh_token)
    return ok_response(data=session.user, message="Login successful")


@router.post("/refresh", response_model=APIResponse[UserOut])
@router.post("/refesh", response_model=APIResponse[UserOut], include_in_schema=False)
@limiter.limit("30/minute")
async def refresh_user_tokens(
    request: Request,
    user_data: UserRefresh,
    response: Response,
    refresh_context: tuple[str, object] = Depends(verify_token_to_refresh),
) -> APIResponse[UserOut]:
    expired_access_token, refresh_record = refresh_context
    if not user_data.refresh_token:
        user_data = UserRefresh(refresh_token=refresh_record.refreshtoken)

    session = await refresh_user_tokens_reduce_number_of_logins(
        user_refresh_data=user_data,
        expired_access_token=expired_access_token,
    )
    set_auth_cookies(response, session.access_token, session.refresh_token)
    return ok_response(data=session.user, message="Session refreshed successfully")


@router.post("/logout", response_model=APIResponse[dict[str, str]])
async def logout(request: Request, response: Response) -> APIResponse[dict[str, str]]:
    await logout_user(
        access_token=request.cookies.get(settings.access_cookie_name),
        refresh_token=request.cookies.get(settings.refresh_cookie_name),
    )
    clear_auth_cookies(response)
    return ok_response(data={"status": "logged_out"}, message="Logout successful")


@router.post("/verify-email", response_model=APIResponse[UserOut])
async def verify_email_endpoint(payload: EmailVerificationRequest) -> APIResponse[UserOut]:
    user = await verify_email(payload.token)
    return ok_response(data=user, message="Email verified successfully")


@router.post("/password-reset/request", response_model=APIResponse[dict[str, str]])
@limiter.limit("5/minute")
async def request_password_reset_endpoint(request: Request, payload: PasswordResetRequest) -> APIResponse[dict[str, str]]:
    await request_password_reset(payload.email)
    return ok_response(
        data={"status": "queued"},
        message="If the account exists, a password reset email has been queued",
    )


@router.post("/password-reset/confirm", response_model=APIResponse[UserOut])
@limiter.limit("5/minute")
async def confirm_password_reset_endpoint(request: Request, payload: PasswordResetConfirm) -> APIResponse[UserOut]:
    user = await confirm_password_reset(payload)
    return ok_response(data=user, message="Password reset successful")


@router.delete("/account", response_model=APIResponse[dict[str, str]], dependencies=[Depends(verify_token)])
async def delete_user_account(
    response: Response,
    token: accessTokenOut = Depends(verify_token),
) -> APIResponse[dict[str, str]]:
    await remove_user(user_id=token.userId)
    clear_auth_cookies(response)
    return ok_response(data={"status": "deleted"}, message="Account deleted successfully")
