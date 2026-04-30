from __future__ import annotations

import logging
import secrets
import string
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client
from bson import ObjectId
from fastapi import HTTPException, status

from core.config import get_settings
from core.database import db
from repositories.tokens_repo import (
    accessTokenCreate,
    add_access_tokens,
    add_refresh_tokens,
    refreshTokenCreate,
)
from repositories.user import create_user, get_user
from schemas.user import UserCreate, UserOut, UserRecord
from services.email_service import enqueue_email
from services.user_service import DEFAULT_STARTER_POWERUPS, AuthSession

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_OAUTH_SCOPE = "openid email profile"

OAUTH_STATE_TTL_SECONDS = 600
USERNAME_ALPHABET = string.ascii_lowercase + string.digits


def _safe_user(user: UserRecord | UserOut) -> UserOut:
    return UserOut.model_validate(user.model_dump())


def _resolve_target(target: Optional[str]) -> tuple[str, dict[str, str]]:
    settings = get_settings()
    targets = settings.google_oauth_redirect_targets
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth redirect targets are not configured",
        )

    chosen = (target or settings.google_oauth_default_target).strip()
    if chosen not in targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown redirect target '{chosen}'",
        )
    return chosen, targets[chosen]


def _ensure_oauth_configured() -> None:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    if not settings.google_oauth_callback_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth callback URL is not configured",
        )


def _build_oauth_client() -> AsyncOAuth2Client:
    settings = get_settings()
    return AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scope=GOOGLE_OAUTH_SCOPE,
        redirect_uri=settings.google_oauth_callback_url,
    )


def _append_query_params(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


async def _generate_unique_username(base: str) -> str:
    cleaned = "".join(ch for ch in base.lower() if ch.isalnum() or ch in "._-")
    cleaned = cleaned.strip("._-") or "player"
    candidate = cleaned[:24] or "player"

    if len(candidate) < 3:
        candidate = (candidate + "player")[:24]

    for _ in range(10):
        existing = await get_user(filter_dict={"username": candidate})
        if existing is None:
            return candidate
        suffix = "".join(secrets.choice(USERNAME_ALPHABET) for _ in range(4))
        base_name = candidate.split("-")[0][:24]
        candidate = f"{base_name}-{suffix}"[:32]

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique username",
    )


async def _create_user_resources(user_id: str) -> None:
    now = int(time.time())
    await db.inventory.insert_one(
        {"user_id": user_id, "items": DEFAULT_STARTER_POWERUPS, "updated_at": now},
    )
    await db.loadouts.insert_one(
        {"user_id": user_id, "slots": ["peek-out", "peek-in", "shield"], "updated_at": now},
    )
    await db.wallets.insert_one(
        {"user_id": user_id, "balance": 1284, "currency": "coins", "updated_at": now},
    )
    await db.notifications.insert_one(
        {
            "user_id": user_id,
            "kind": "system",
            "title": "Welcome to Dead & Injured",
            "body": "Your inventory and wallet are ready.",
            "unread": True,
            "created_at": now,
        },
    )


async def _rollback_signup(user_id: str) -> None:
    await db.users.delete_one({"_id": ObjectId(user_id)})
    await db.inventory.delete_many({"user_id": user_id})
    await db.loadouts.delete_many({"user_id": user_id})
    await db.wallets.delete_many({"user_id": user_id})
    await db.notifications.delete_many({"user_id": user_id})


async def _issue_session(user_id: str) -> tuple[str, str]:
    access_token = await add_access_tokens(token_data=accessTokenCreate(userId=user_id))
    refresh_token = await add_refresh_tokens(
        token_data=refreshTokenCreate(
            userId=user_id,
            previousAccessToken=access_token.accesstoken,
        ),
    )
    return access_token.accesstoken, refresh_token.refreshtoken


@dataclass(frozen=True)
class GoogleAuthorizeResult:
    authorize_url: str
    state: str
    target: str


async def build_authorize_url(target: Optional[str]) -> GoogleAuthorizeResult:
    _ensure_oauth_configured()
    chosen_target, _ = _resolve_target(target)

    client = _build_oauth_client()
    try:
        authorize_url, state = client.create_authorization_url(
            GOOGLE_AUTHORIZE_URL,
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
    finally:
        await client.aclose()

    now = int(time.time())
    await db.google_oauth_states.insert_one(
        {
            "state": state,
            "target": chosen_target,
            "created_at": now,
            "expires_at": now + OAUTH_STATE_TTL_SECONDS,
            "used": False,
        },
    )
    return GoogleAuthorizeResult(authorize_url=authorize_url, state=state, target=chosen_target)


async def _consume_state(state: str) -> str:
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state")
    record = await db.google_oauth_states.find_one_and_delete({"state": state})
    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    if record.get("expires_at", 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state expired")
    return record["target"]


async def _exchange_authorization_code(code: str) -> dict:
    client = _build_oauth_client()
    try:
        token = await client.fetch_token(
            GOOGLE_TOKEN_URL,
            code=code,
            grant_type="authorization_code",
        )
        return dict(token)
    finally:
        await client.aclose()


async def _fetch_userinfo(access_token: str) -> dict:
    client = _build_oauth_client()
    try:
        client.token = {"access_token": access_token, "token_type": "Bearer"}
        response = await client.get(GOOGLE_USERINFO_URL)
        response.raise_for_status()
        return response.json()
    finally:
        await client.aclose()


async def _find_or_create_user(profile: dict) -> tuple[UserOut, bool]:
    email = profile.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account did not return an email address",
        )

    existing = await get_user(filter_dict={"email": email})
    if existing is not None:
        update_fields: dict[str, object] = {}
        if not existing.is_email_verified and bool(profile.get("verified_email", True)):
            update_fields["is_email_verified"] = True
        avatar = profile.get("picture")
        if avatar and not existing.avatar_url:
            update_fields["avatar_url"] = avatar
            update_fields["profile_media_url"] = avatar
            update_fields["profile_media_kind"] = "image"
        if update_fields:
            update_fields["last_updated"] = int(time.time())
            await db.users.update_one({"_id": ObjectId(existing.id)}, {"$set": update_fields})
            existing = await get_user(filter_dict={"_id": ObjectId(existing.id)})
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to refresh user after profile update",
                )
        return _safe_user(existing), False

    base_username = profile.get("given_name") or email.split("@", 1)[0]
    username = await _generate_unique_username(base_username)

    random_password = secrets.token_urlsafe(32) + "Aa1"
    avatar_url = profile.get("picture")
    payload = {
        "email": email,
        "username": username,
        "password": random_password,
        "is_email_verified": bool(profile.get("verified_email", True)),
    }
    if avatar_url:
        payload["avatar_url"] = avatar_url
        payload["profile_media_url"] = avatar_url
        payload["profile_media_kind"] = "image"

    new_user = await create_user(UserCreate(**payload))
    try:
        await _create_user_resources(new_user.id)
    except Exception:
        await _rollback_signup(new_user.id)
        raise
    return new_user, True


async def _store_exchange_record(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> str:
    settings = get_settings()
    code = secrets.token_urlsafe(32)
    now = int(time.time())
    await db.google_oauth_exchanges.insert_one(
        {
            "code": code,
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": now,
            "expires_at": now + settings.google_oauth_exchange_ttl_seconds,
            "used": False,
        },
    )
    return code


@dataclass(frozen=True)
class GoogleCallbackResult:
    redirect_url: str
    target: str


async def handle_callback(
    code: Optional[str],
    state: Optional[str],
    error: Optional[str] = None,
) -> GoogleCallbackResult:
    _ensure_oauth_configured()

    if not state:
        settings = get_settings()
        fallback_target = settings.google_oauth_default_target
        if fallback_target in settings.google_oauth_redirect_targets:
            error_url = settings.google_oauth_redirect_targets[fallback_target]["error"]
            return GoogleCallbackResult(
                redirect_url=_append_query_params(error_url, {"reason": "missing_state"}),
                target=fallback_target,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state")

    target = await _consume_state(state)
    _, target_urls = _resolve_target(target)

    if error:
        logger.info("Google OAuth callback returned error: %s", error)
        return GoogleCallbackResult(
            redirect_url=_append_query_params(target_urls["error"], {"reason": error}),
            target=target,
        )

    if not code:
        return GoogleCallbackResult(
            redirect_url=_append_query_params(target_urls["error"], {"reason": "missing_code"}),
            target=target,
        )

    try:
        token = await _exchange_authorization_code(code)
        google_access_token = token.get("access_token")
        if not google_access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google did not return an access token",
            )
        profile = await _fetch_userinfo(google_access_token)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to complete Google OAuth token exchange")
        return GoogleCallbackResult(
            redirect_url=_append_query_params(target_urls["error"], {"reason": "exchange_failed"}),
            target=target,
        )

    try:
        user, is_new = await _find_or_create_user(profile)
        access_token, refresh_token = await _issue_session(user.id)
    except HTTPException as exc:
        logger.info("Google OAuth user provisioning failed: %s", exc.detail)
        return GoogleCallbackResult(
            redirect_url=_append_query_params(target_urls["error"], {"reason": "provisioning_failed"}),
            target=target,
        )
    except Exception:
        logger.exception("Failed to provision user from Google profile")
        return GoogleCallbackResult(
            redirect_url=_append_query_params(target_urls["error"], {"reason": "provisioning_failed"}),
            target=target,
        )

    if is_new:
        logger.info("Provisioned new Google user user_id=%s email=%s", user.id, user.email)
    else:
        enqueue_email(
            kind="new_signin",
            payload={
                "receiver_email": user.email,
                "username": user.username,
            },
        )

    exchange_code = await _store_exchange_record(user.id, access_token, refresh_token)
    success_url = _append_query_params(target_urls["success"], {"code": exchange_code})
    return GoogleCallbackResult(redirect_url=success_url, target=target)


async def consume_exchange_code(code: str) -> AuthSession:
    record = await db.google_oauth_exchanges.find_one_and_delete({"code": code})
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exchange code not found or already used",
        )
    if record.get("expires_at", 0) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Exchange code expired",
        )

    user = await get_user(filter_dict={"_id": ObjectId(record["user_id"])})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User no longer exists",
        )
    return AuthSession(
        user=_safe_user(user),
        access_token=record["access_token"],
        refresh_token=record["refresh_token"],
    )
