from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


_DEFAULT_CORS_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
_DEFAULT_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
    "X-CSRF-Token",
]


def _split_csv(raw_value: str, default: list[str]) -> list[str]:
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    return values or default


@dataclass(frozen=True)
class Settings:
    app_name: str
    env: str
    root_path: str
    api_prefix: str
    cors_origins: list[str]
    cors_methods: list[str]
    cors_headers: list[str]
    access_cookie_name: str
    refresh_cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    access_token_ttl_days: int
    refresh_token_ttl_days: int
    email_verification_ttl_minutes: int
    password_reset_ttl_minutes: int
    password_reset_url: str
    email_verification_url: str
    resend_api_key: str
    resend_from_email: str
    resend_from_name: str
    max_user_page_size: int
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("ENV", "development").lower()

        cors_origins = _split_csv(
            os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"),
            ["http://localhost:3000", "http://127.0.0.1:3000"],
        )
        cors_methods = _split_csv(os.getenv("CORS_METHODS", ""), _DEFAULT_CORS_METHODS)
        cors_headers = _split_csv(os.getenv("CORS_HEADERS", ""), _DEFAULT_CORS_HEADERS)

        cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            cookie_samesite = "lax"
        if env == "production" and cookie_samesite == "none":
            cookie_samesite = "strict"

        cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
        if env == "production" and not cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true when ENV=production")

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        return cls(
            app_name=os.getenv("APP_NAME", "Dead and Injured API"),
            env=env,
            root_path=os.getenv("API_ROOT_PATH", "/api/v1"),
            api_prefix=os.getenv("API_PREFIX", "/api/v1"),
            cors_origins=cors_origins,
            cors_methods=cors_methods,
            cors_headers=cors_headers,
            access_cookie_name=os.getenv("ACCESS_COOKIE_NAME", "di_access"),
            refresh_cookie_name=os.getenv("REFRESH_COOKIE_NAME", "di_refresh"),
            cookie_secure=cookie_secure,
            cookie_samesite=cookie_samesite,
            access_token_ttl_days=int(os.getenv("ACCESS_TOKEN_TTL_DAYS", "10")),
            refresh_token_ttl_days=int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "30")),
            email_verification_ttl_minutes=int(os.getenv("EMAIL_VERIFICATION_TTL_MINUTES", "30")),
            password_reset_ttl_minutes=int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "15")),
            password_reset_url=os.getenv(
                "PASSWORD_RESET_URL",
                "http://localhost:3000/reset-password",
            ),
            email_verification_url=os.getenv(
                "EMAIL_VERIFICATION_URL",
                "http://localhost:3000/verify-email",
            ),
            resend_api_key=os.getenv("RESEND_API_KEY", ""),
            resend_from_email=os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev"),
            resend_from_name=os.getenv("RESEND_FROM_NAME", "Dead & Injured"),
            max_user_page_size=int(os.getenv("MAX_USER_PAGE_SIZE", "100")),
            redis_url=redis_url,
            celery_broker_url=os.getenv("CELERY_BROKER_URL", redis_url),
            celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
