from __future__ import annotations

from fastapi import Response

from core.config import get_settings


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    domain = settings.cookie_domain or None
    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
        domain=domain,
        max_age=settings.access_token_ttl_days * 24 * 60 * 60,
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
        domain=domain,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    domain = settings.cookie_domain or None
    response.delete_cookie(settings.access_cookie_name, path="/", domain=domain)
    response.delete_cookie(settings.refresh_cookie_name, path="/", domain=domain)

