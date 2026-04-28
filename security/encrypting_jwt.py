import datetime
import logging
import os
import random
from datetime import timezone

import jwt
from bson import ObjectId
from dotenv import load_dotenv

from core.database import db

load_dotenv()
SECRETID = os.getenv("SECRETID")

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Base error raised when a JWT cannot be validated."""


class TokenExpiredError(TokenError):
    """Raised when the token's signature has expired."""


class TokenInvalidError(TokenError):
    """Raised when the token is malformed or signed with an unknown key."""


_secret_cache: dict[str, str] | None = None


async def _load_secret_dict() -> dict[str, str]:
    if not SECRETID:
        raise RuntimeError("SECRETID environment variable is not set")
    result = await db.secret_keys.find_one({"_id": ObjectId(SECRETID)})
    if not result:
        raise RuntimeError("JWT signing secrets not found in database")
    result.pop("_id", None)
    if not result:
        raise RuntimeError("JWT signing secrets payload is empty")
    return {str(k): str(v) for k, v in result.items()}


async def get_secret_dict() -> dict[str, str]:
    global _secret_cache
    if _secret_cache is None:
        _secret_cache = await _load_secret_dict()
    return _secret_cache


async def get_secret_and_header():
    secrets = await get_secret_dict()
    random_key = random.choice(list(secrets.keys()))
    random_secret = secrets[random_key]
    return {
        "SECRET_KEY": {random_key: random_secret},
        "HEADERS": {"kid": random_key},
    }


async def create_jwt_member_token(token):
    secrets = await get_secret_and_header()
    SECRET_KEYS = secrets["SECRET_KEY"]
    headers = secrets["HEADERS"]

    payload = {
        "accessToken": token,
        "role": "member",
        "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=15),
    }

    return jwt.encode(payload, SECRET_KEYS[headers["kid"]], algorithm="HS256", headers=headers)


async def create_jwt_admin_token(token):
    secrets = await get_secret_and_header()
    SECRET_KEYS = secrets["SECRET_KEY"]
    headers = secrets["HEADERS"]

    payload = {
        "accessToken": token,
        "role": "admin",
        "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=15),
    }

    return jwt.encode(payload, SECRET_KEYS[headers["kid"]], algorithm="HS256", headers=headers)


async def decode_jwt_token(token):
    """Decode a JWT and return the payload.

    Raises TokenExpiredError if the signature has expired and TokenInvalidError
    if the token is malformed, has an unknown kid, or fails verification.
    Returns None only when the input token is falsy so callers can treat
    "no token" distinctly from "bad token".
    """
    if not token:
        return None

    SECRET_KEYS = await get_secret_dict()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise TokenInvalidError("Malformed token") from exc

    kid = unverified_header.get("kid")
    key = SECRET_KEYS.get(kid) if kid else None
    if not key:
        raise TokenInvalidError("Unknown key ID")

    try:
        return jwt.decode(token, key, algorithms=["HS256"])
    except jwt.exceptions.ExpiredSignatureError as exc:
        raise TokenExpiredError("Token expired") from exc
    except jwt.exceptions.InvalidSignatureError as exc:
        raise TokenInvalidError("Invalid signature") from exc
    except jwt.exceptions.DecodeError as exc:
        raise TokenInvalidError("Malformed token") from exc


async def decode_jwt_token_without_expiration(token):
    if not token:
        return None

    SECRET_KEYS = await get_secret_dict()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise TokenInvalidError("Malformed token") from exc

    kid = unverified_header.get("kid")
    key = SECRET_KEYS.get(kid) if kid else None
    if not key:
        raise TokenInvalidError("Unknown key ID")

    try:
        return jwt.decode(token, key, algorithms=["HS256"])
    except jwt.exceptions.ExpiredSignatureError:
        return jwt.decode(token, key, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.exceptions.DecodeError as exc:
        raise TokenInvalidError("Malformed token") from exc
