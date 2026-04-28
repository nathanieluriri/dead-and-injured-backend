from __future__ import annotations

import hashlib

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import get_settings


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def _identify_request(request: Request) -> str:
    settings = get_settings()
    cookie = request.cookies.get(settings.access_cookie_name)
    if cookie:
        return f"session:{_hash_token(cookie)}"
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return f"session:{_hash_token(token)}"
    return get_remote_address(request)


limiter = Limiter(key_func=_identify_request)
