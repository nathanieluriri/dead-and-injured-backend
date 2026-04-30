from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import List

from bson import ObjectId
from fastapi import HTTPException, status

from core.config import get_settings
from core.database import db
from repositories.tokens_repo import (
    accessTokenCreate,
    add_access_tokens,
    add_refresh_tokens,
    delete_access_token,
    delete_all_tokens_with_user_id,
    delete_refresh_token,
    get_refresh_tokens,
    refreshTokenCreate,
)
from repositories.user import create_user, delete_user, get_user, get_users, update_user
from security.hash import check_password, hash_password
from schemas.tokens_schema import accessTokenOut, refreshTokenOut
from schemas.user import (
    PasswordResetConfirm,
    UserCreate,
    UserLogin,
    UserOut,
    UserRefresh,
    UserRecord,
    UserSignup,
    UserUpdate,
)
from services.email_service import EmailDispatch, enqueue_email

DEFAULT_STARTER_POWERUPS: list[dict[str, str | int]] = [
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

settings = get_settings()


@dataclass(frozen=True)
class AuthSession:
    user: UserOut
    access_token: str
    refresh_token: str
    verification_email: EmailDispatch = EmailDispatch.QUEUED


def _safe_user(user: UserRecord | UserOut) -> UserOut:
    return UserOut.model_validate(user.model_dump())


async def _issue_session(user_id: str) -> tuple[accessTokenOut, refreshTokenOut]:
    access_token = await add_access_tokens(token_data=accessTokenCreate(userId=user_id))
    refresh_token = await add_refresh_tokens(
        token_data=refreshTokenCreate(
            userId=user_id,
            previousAccessToken=access_token.accesstoken,
        )
    )
    return access_token, refresh_token


async def _create_email_verification(user: UserOut) -> str:
    token = secrets.token_urlsafe(24)
    await db.email_verification_tokens.insert_one(
        {
            "user_id": user.id,
            "token": token,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + settings.email_verification_ttl_minutes * 60,
            "used": False,
        }
    )
    return token


async def _rollback_signup(user_id: str) -> None:
    await db.users.delete_one({"_id": ObjectId(user_id)})
    await db.inventory.delete_many({"user_id": user_id})
    await db.loadouts.delete_many({"user_id": user_id})
    await db.wallets.delete_many({"user_id": user_id})
    await db.notifications.delete_many({"user_id": user_id})
    await db.email_verification_tokens.delete_many({"user_id": user_id})


async def add_user(user_data: UserSignup) -> AuthSession:
    existing_user = await get_user(filter_dict={"email": user_data.email})
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    existing_username = await get_user(filter_dict={"username": user_data.username})
    if existing_username is not None:
        raise HTTPException(status_code=409, detail="Username already exists")

    new_user = await create_user(UserCreate(**user_data.model_dump()))
    try:
        now = int(time.time())
        await db.inventory.insert_one({"user_id": new_user.id, "items": DEFAULT_STARTER_POWERUPS, "updated_at": now})
        await db.loadouts.insert_one({"user_id": new_user.id, "slots": ["peek-out", "peek-in", "shield"], "updated_at": now})
        await db.wallets.insert_one({"user_id": new_user.id, "balance": 1284, "currency": "coins", "updated_at": now})
        await db.notifications.insert_one(
            {
                "user_id": new_user.id,
                "kind": "system",
                "title": "Welcome to Dead & Injured",
                "body": "Your inventory and wallet are ready.",
                "unread": True,
                "created_at": now,
            }
        )
        access_token, refresh_token = await _issue_session(new_user.id)
        verification_token = await _create_email_verification(new_user)
    except Exception:
        await _rollback_signup(new_user.id)
        raise

    dispatch = enqueue_email(
        kind="verify_email",
        payload={
            "receiver_email": new_user.email,
            "username": new_user.username,
            "token": verification_token,
        },
    )
    return AuthSession(
        user=new_user,
        access_token=access_token.accesstoken,
        refresh_token=refresh_token.refreshtoken,
        verification_email=dispatch,
    )


async def authenticate_user(user_data: UserLogin) -> AuthSession:
    user = await get_user(filter_dict={"email": user_data.email})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not check_password(password=user_data.password, hashed=user.password):
        raise HTTPException(status_code=401, detail="Unauthorized, invalid login credentials")

    access_token, refresh_token = await _issue_session(user.id)
    enqueue_email(
        kind="new_signin",
        payload={
            "receiver_email": user.email,
            "username": user.username,
        },
    )
    return AuthSession(
        user=_safe_user(user),
        access_token=access_token.accesstoken,
        refresh_token=refresh_token.refreshtoken,
    )


async def refresh_user_tokens_reduce_number_of_logins(
    user_refresh_data: UserRefresh,
    expired_access_token: str,
) -> AuthSession:
    refresh_token_value = user_refresh_data.refresh_token
    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    refresh_object = await get_refresh_tokens(refresh_token_value)
    if refresh_object is None:
        raise HTTPException(status_code=404, detail="Invalid refresh token")

    if refresh_object.previousAccessToken != expired_access_token:
        await delete_refresh_token(refreshToken=refresh_token_value)
        await delete_access_token(accessToken=expired_access_token)
        raise HTTPException(status_code=401, detail="Refresh token does not match session")

    user = await get_user(filter_dict={"_id": ObjectId(refresh_object.userId)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    access_token, refresh_token = await _issue_session(user.id)
    await delete_access_token(accessToken=expired_access_token)
    await delete_refresh_token(refreshToken=refresh_token_value)
    return AuthSession(
        user=_safe_user(user),
        access_token=access_token.accesstoken,
        refresh_token=refresh_token.refreshtoken,
    )


async def logout_user(access_token: str | None, refresh_token: str | None) -> None:
    import logging

    from bson.errors import InvalidId
    from pymongo.errors import PyMongoError

    logger = logging.getLogger(__name__)

    if access_token:
        try:
            await delete_access_token(accessToken=access_token)
        except (InvalidId, PyMongoError, HTTPException) as exc:
            logger.warning("logout: failed to delete access token: %s", exc)
    if refresh_token:
        try:
            await delete_refresh_token(refreshToken=refresh_token)
        except (InvalidId, PyMongoError, HTTPException) as exc:
            logger.warning("logout: failed to delete refresh token: %s", exc)


async def remove_user(user_id: str) -> None:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    filter_dict = {"_id": ObjectId(user_id)}
    result = await delete_user(filter_dict)
    await delete_all_tokens_with_user_id(userId=user_id)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")


async def retrieve_user_by_user_id(id: str) -> UserOut:
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_user(filter_dict)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _safe_user(result)


async def retrieve_users(start: int = 0, stop: int = 100) -> List[UserOut]:
    if start < 0:
        raise HTTPException(status_code=400, detail="start must be >= 0")
    max_page = settings.max_user_page_size
    if stop <= start:
        raise HTTPException(status_code=400, detail="stop must be greater than start")
    if stop - start > max_page:
        stop = start + max_page
    return await get_users(start=start, stop=stop)


async def update_user_by_id(user_id: str, user_data: UserUpdate) -> UserOut:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    if user_data.username:
        current = await get_user(filter_dict={"_id": ObjectId(user_id)})
        if current is None:
            raise HTTPException(status_code=404, detail="User not found")
        if current.is_guest and user_data.username != current.username:
            raise HTTPException(
                status_code=403,
                detail="Guest accounts cannot change usernames. Upgrade to a full account first.",
            )
        existing_user = await get_user(filter_dict={"username": user_data.username})
        if existing_user is not None and existing_user.id != user_id:
            raise HTTPException(status_code=409, detail="Username already exists")

    filter_dict = {"_id": ObjectId(user_id)}
    result = await update_user(filter_dict, user_data)
    if not result:
        raise HTTPException(status_code=404, detail="User not found or update failed")
    return result


async def verify_email(token: str) -> UserOut:
    record = await db.email_verification_tokens.find_one({"token": token, "used": False})
    if record is None:
        raise HTTPException(status_code=404, detail="Verification token not found")
    if record["expires_at"] < int(time.time()):
        raise HTTPException(status_code=401, detail="Verification token expired")

    user_id = record["user_id"]
    await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_email_verified": True, "last_updated": int(time.time())}},
    )
    await db.email_verification_tokens.find_one_and_update(
        {"_id": record["_id"]},
        {"$set": {"used": True}},
    )
    return await retrieve_user_by_user_id(user_id)


async def request_password_reset(email: str) -> EmailDispatch:
    """Always returns QUEUED.

    The unknown-email branch short-circuits before ever calling the broker,
    so a real broker outage would otherwise produce DELAYED for known emails
    and QUEUED for unknown ones — turning the response into a free
    broker-health probe and (for an attacker who already knows broker state)
    an account-existence oracle. Until the unknown-email branch can probe
    broker health symmetrically, both branches report QUEUED. The actual
    enqueue outcome is still logged inside enqueue_email for ops.
    """
    user = await get_user(filter_dict={"email": email})
    if user is None:
        return EmailDispatch.QUEUED

    token = secrets.token_urlsafe(24)
    await db.password_reset_tokens.insert_one(
        {
            "user_id": user.id,
            "token": token,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + settings.password_reset_ttl_minutes * 60,
            "used": False,
        }
    )
    enqueue_email(
        kind="password_reset",
        payload={
            "receiver_email": user.email,
            "username": user.username,
            "token": token,
        },
    )
    return EmailDispatch.QUEUED


async def resend_email_verification(user_id: str) -> EmailDispatch:
    user = await retrieve_user_by_user_id(user_id)
    if user.is_email_verified:
        raise HTTPException(status_code=409, detail="Email already verified")

    verification_token = await _create_email_verification(user)
    return enqueue_email(
        kind="verify_email",
        payload={
            "receiver_email": user.email,
            "username": user.username,
            "token": verification_token,
        },
    )


async def confirm_password_reset(payload: PasswordResetConfirm) -> UserOut:
    reset_record = await db.password_reset_tokens.find_one({"token": payload.token, "used": False})
    if reset_record is None:
        raise HTTPException(status_code=404, detail="Password reset token not found")
    if reset_record["expires_at"] < int(time.time()):
        raise HTTPException(status_code=401, detail="Password reset token expired")

    user_id = reset_record["user_id"]
    await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"password": hash_password(payload.password), "last_updated": int(time.time())}},
    )
    await db.password_reset_tokens.find_one_and_update(
        {"_id": reset_record["_id"]},
        {"$set": {"used": True}},
    )
    await delete_all_tokens_with_user_id(userId=user_id)
    return await retrieve_user_by_user_id(user_id)
