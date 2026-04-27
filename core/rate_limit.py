from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import get_settings


def _identify_request(request: Request) -> str:
    settings = get_settings()
    cookie = request.cookies.get(settings.access_cookie_name)
    if cookie:
        return f"session:{cookie}"
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return f"session:{auth_header[7:].strip()}"
    return get_remote_address(request)


limiter = Limiter(key_func=_identify_request)
