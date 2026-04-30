from __future__ import annotations

import logging
import secrets
import string
import time

from bson import ObjectId
from fastapi import HTTPException, status

from core.config import get_settings
from core.database import db
from repositories.tokens_repo import (
    accessTokenCreate,
    add_access_tokens,
    add_refresh_tokens,
    delete_all_tokens_with_user_id,
    refreshTokenCreate,
)
from repositories.user import create_user, get_user
from schemas.user import GuestUpgradeRequest, UserCreate, UserOut, UserRecord
from security.hash import hash_password
from services.email_service import EmailDispatch, enqueue_email
from services.user_service import (
    DEFAULT_STARTER_POWERUPS,
    AuthSession,
    _create_email_verification,
)

logger = logging.getLogger(__name__)

GUEST_EMAIL_DOMAIN = "guest.dead-and-injured.example"
GUEST_USERNAME_PREFIX = "guest"
GUEST_TOKEN_ALPHABET = string.ascii_lowercase + string.digits


def _safe_user(user: UserRecord | UserOut) -> UserOut:
    return UserOut.model_validate(user.model_dump())


def _random_handle(length: int = 10) -> str:
    return "".join(secrets.choice(GUEST_TOKEN_ALPHABET) for _ in range(length))


async def _generate_unique_guest_username() -> str:
    for _ in range(10):
        candidate = f"{GUEST_USERNAME_PREFIX}-{_random_handle(8)}"
        existing = await get_user(filter_dict={"username": candidate})
        if existing is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique guest username",
    )


async def _generate_unique_guest_email() -> str:
    for _ in range(10):
        candidate = f"guest-{_random_handle(16)}@{GUEST_EMAIL_DOMAIN}"
        existing = await get_user(filter_dict={"email": candidate})
        if existing is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique guest email",
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
            "title": "Welcome, guest!",
            "body": "Your guest session is ready. Upgrade to a full account to keep your progress past expiry.",
            "unread": True,
            "created_at": now,
        },
    )


async def _rollback_guest_signup(user_id: str) -> None:
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


async def create_guest_session() -> AuthSession:
    """Provision a brand new guest user with default resources and an auth session.

    Guests get a synthetic email/username and an unguessable random password they
    cannot use. The user is marked is_guest=True with an explicit expires_at
    timestamp so an out-of-band cleanup task can purge stale guests.
    """
    settings = get_settings()
    username = await _generate_unique_guest_username()
    email = await _generate_unique_guest_email()
    random_password = secrets.token_urlsafe(32) + "Aa1"

    now = int(time.time())
    expires_at = now + settings.guest_user_ttl_days * 24 * 60 * 60

    payload = {
        "email": email,
        "username": username,
        "password": random_password,
        "is_email_verified": False,
        "is_guest": True,
        "expires_at": expires_at,
    }

    new_user = await create_user(UserCreate(**payload))
    try:
        await _create_user_resources(new_user.id)
        access_token, refresh_token = await _issue_session(new_user.id)
    except Exception:
        await _rollback_guest_signup(new_user.id)
        raise

    logger.info(
        "Provisioned guest user user_id=%s username=%s expires_at=%s",
        new_user.id,
        new_user.username,
        expires_at,
    )
    return AuthSession(
        user=_safe_user(new_user),
        access_token=access_token,
        refresh_token=refresh_token,
        verification_email=EmailDispatch.QUEUED,
    )


async def upgrade_guest_to_user(user_id: str, payload: GuestUpgradeRequest) -> AuthSession:
    """Convert an existing guest account into a real user.

    The caller must already be authenticated as the guest. The endpoint that
    invokes this should pass the authenticated user_id from the access token.
    Issues a fresh access/refresh pair and invalidates all prior guest tokens
    so a leaked guest cookie cannot continue acting as the upgraded user.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    user = await get_user(filter_dict={"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_guest:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account is not a guest account",
        )

    email = payload.email.lower()
    email_owner = await get_user(filter_dict={"email": email})
    if email_owner is not None and email_owner.id != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    desired_username = payload.username.strip() if payload.username else user.username
    if desired_username != user.username:
        username_owner = await get_user(filter_dict={"username": desired_username})
        if username_owner is not None and username_owner.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

    now = int(time.time())
    update_fields: dict[str, object] = {
        "email": email,
        "password": hash_password(payload.password),
        "username": desired_username,
        "is_guest": False,
        "expires_at": None,
        "is_email_verified": False,
        "last_updated": now,
    }
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_fields})

    refreshed = await get_user(filter_dict={"_id": ObjectId(user_id)})
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load user after upgrade",
        )

    # Burn every token issued while the account was a guest, then mint a fresh
    # session for the now-real user.
    await delete_all_tokens_with_user_id(userId=user_id)
    access_token, refresh_token = await _issue_session(user_id)
    verification_token = await _create_email_verification(_safe_user(refreshed))
    dispatch = enqueue_email(
        kind="verify_email",
        payload={
            "receiver_email": refreshed.email,
            "username": refreshed.username,
            "token": verification_token,
        },
    )
    logger.info("Upgraded guest user user_id=%s to real account email=%s", user_id, email)
    return AuthSession(
        user=_safe_user(refreshed),
        access_token=access_token,
        refresh_token=refresh_token,
        verification_email=dispatch,
    )
