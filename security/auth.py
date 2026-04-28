from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings
from repositories.tokens_repo import (
    get_access_tokens,
    get_access_tokens_no_date_check,
    get_refresh_token_owner,
)
from schemas.tokens_schema import accessTokenOut, refreshTokenOut

settings = get_settings()
token_auth_scheme = HTTPBearer(auto_error=False)


async def _extract_token_value(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    cookie_name: str,
) -> str | None:
    if request.cookies.get(cookie_name):
        return request.cookies.get(cookie_name)
    if credentials is not None:
        return credentials.credentials
    return None


async def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(token_auth_scheme),
) -> accessTokenOut:
    token_value = await _extract_token_value(
        request=request,
        credentials=credentials,
        cookie_name=settings.access_cookie_name,
    )
    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    result = await get_access_tokens(accessToken=token_value)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return result


async def verify_token_email_verified(
    token: accessTokenOut = Depends(verify_token),
) -> accessTokenOut:
    """Authenticated dependency that also requires the user's email to be verified."""
    from bson import ObjectId
    from core.database import db

    user = await db.users.find_one({"_id": ObjectId(token.userId)})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    if not user.get("is_email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return token


async def verify_token_to_refresh(request: Request) -> tuple[str, refreshTokenOut]:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )
    refresh_record = await get_refresh_token_owner(refresh_token)
    if refresh_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    access_token = request.cookies.get(settings.access_cookie_name) or refresh_record.previousAccessToken
    return access_token, refresh_record


async def verify_access_token_without_expiration(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(token_auth_scheme),
) -> accessTokenOut:
    token_value = await _extract_token_value(
        request=request,
        credentials=credentials,
        cookie_name=settings.access_cookie_name,
    )
    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    result = await get_access_tokens_no_date_check(accessToken=token_value)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return result


async def maybe_verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(token_auth_scheme),
) -> accessTokenOut | None:
    token_value = await _extract_token_value(
        request=request,
        credentials=credentials,
        cookie_name=settings.access_cookie_name,
    )
    if not token_value:
        return None
    return await get_access_tokens(accessToken=token_value)
