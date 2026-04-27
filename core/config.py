from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _split_csv(raw_value: str, default: list[str]) -> list[str]:
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    return values or default


@dataclass(frozen=True)
class Settings:
    app_name: str
    root_path: str
    api_prefix: str
    cors_origins: list[str]
    access_cookie_name: str
    refresh_cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    access_token_ttl_days: int
    refresh_token_ttl_days: int
    email_verification_ttl_minutes: int
    password_reset_ttl_minutes: int
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    @classmethod
    def from_env(cls) -> "Settings":
        cors_origins = _split_csv(
            os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"),
            ["http://localhost:3000", "http://127.0.0.1:3000"],
        )
        cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            cookie_samesite = "lax"

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return cls(
            app_name=os.getenv("APP_NAME", "Dead and Injured API"),
            root_path=os.getenv("API_ROOT_PATH", "/api/v1"),
            api_prefix=os.getenv("API_PREFIX", "/api/v1"),
            cors_origins=cors_origins,
            access_cookie_name=os.getenv("ACCESS_COOKIE_NAME", "di_access"),
            refresh_cookie_name=os.getenv("REFRESH_COOKIE_NAME", "di_refresh"),
            cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            cookie_samesite=cookie_samesite,
            access_token_ttl_days=int(os.getenv("ACCESS_TOKEN_TTL_DAYS", "10")),
            refresh_token_ttl_days=int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "30")),
            email_verification_ttl_minutes=int(os.getenv("EMAIL_VERIFICATION_TTL_MINUTES", "30")),
            password_reset_ttl_minutes=int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "15")),
            redis_url=redis_url,
            celery_broker_url=os.getenv("CELERY_BROKER_URL", redis_url),
            celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
