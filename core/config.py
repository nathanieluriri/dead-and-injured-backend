from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


_DEFAULT_CORS_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
_DEFAULT_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
    "X-CSRF-Token",
]
_BROWSER_ORIGIN_SCHEMES = {"http", "https"}

# Always-trusted browser origins, regardless of env. Add the deployed frontend
# hostnames here so that the OAuth + cookie flow works even if CORS_ORIGINS or
# GOOGLE_OAUTH_REDIRECT_TARGETS is misconfigured for an environment.
_ALWAYS_ALLOWED_ORIGINS: list[str] = [
    "https://guess-grid.vercel.app",
]


def _split_csv(raw_value: str, default: list[str]) -> list[str]:
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    return values or default


def _parse_google_redirect_targets(raw_value: str) -> dict[str, dict[str, str]]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("GOOGLE_OAUTH_REDIRECT_TARGETS is not valid JSON; ignoring")
        return {}

    if not isinstance(parsed, dict):
        logger.warning("GOOGLE_OAUTH_REDIRECT_TARGETS must be a JSON object; ignoring")
        return {}

    cleaned: dict[str, dict[str, str]] = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            continue
        success = value.get("success")
        error = value.get("error")
        if not isinstance(success, str) or not isinstance(error, str):
            continue
        cleaned[str(key)] = {"success": success, "error": error}
    return cleaned


def _origin_from_url(url: str) -> str | None:
    """Return the browser-origin (scheme://host[:port]) for a URL, or None."""
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return None
    if parsed.scheme not in _BROWSER_ORIGIN_SCHEMES or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    default_port = 443 if parsed.scheme == "https" else 80
    if parsed.port and parsed.port != default_port:
        return f"{parsed.scheme}://{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _origins_from_redirect_targets(targets: dict[str, dict[str, str]]) -> list[str]:
    seen: list[str] = []
    for value in targets.values():
        for url in (value.get("success"), value.get("error")):
            if not url:
                continue
            origin = _origin_from_url(url)
            if origin and origin not in seen:
                seen.append(origin)
    return seen


def _merge_origins(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for origin in group:
            if origin and origin not in merged:
                merged.append(origin)
    return merged


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
    cookie_domain: str
    access_token_ttl_days: int
    refresh_token_ttl_days: int
    email_verification_ttl_minutes: int
    password_reset_ttl_minutes: int
    password_reset_url: str
    email_verification_url: str
    resend_api_key: str
    resend_from_email: str
    resend_from_name: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_endpoint_url: str
    r2_bucket: str
    public_base_url: str
    profile_media_max_bytes: int
    profile_video_max_bytes: int
    max_user_page_size: int
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    google_client_id: str
    google_client_secret: str
    google_oauth_callback_url: str
    google_oauth_default_target: str
    google_oauth_exchange_ttl_seconds: int
    guest_user_ttl_days: int
    google_oauth_redirect_targets: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("ENV", "development").lower()

        google_redirect_targets = _parse_google_redirect_targets(
            os.getenv("GOOGLE_OAUTH_REDIRECT_TARGETS", ""),
        )
        cors_origins = _merge_origins(
            _split_csv(
                os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"),
                ["http://localhost:3000", "http://127.0.0.1:3000"],
            ),
            _origins_from_redirect_targets(google_redirect_targets),
            _ALWAYS_ALLOWED_ORIGINS,
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

        cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip()

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        google_default_target = os.getenv("GOOGLE_OAUTH_DEFAULT_TARGET", "local").strip() or "local"

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
            cookie_domain=cookie_domain,
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
            r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID", ""),
            r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", ""),
            r2_endpoint_url=os.getenv("R2_ENDPOINT_URL", ""),
            r2_bucket=os.getenv("R2_BUCKET", ""),
            public_base_url=os.getenv("PUBLIC_BASE_URL", ""),
            profile_media_max_bytes=int(os.getenv("PROFILE_MEDIA_MAX_BYTES", str(12 * 1024 * 1024))),
            profile_video_max_bytes=int(os.getenv("PROFILE_VIDEO_MAX_BYTES", str(40 * 1024 * 1024))),
            max_user_page_size=int(os.getenv("MAX_USER_PAGE_SIZE", "100")),
            redis_url=redis_url,
            celery_broker_url=os.getenv("CELERY_BROKER_URL", redis_url),
            celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
            google_oauth_callback_url=os.getenv("GOOGLE_OAUTH_CALLBACK_URL", ""),
            google_oauth_default_target=google_default_target,
            google_oauth_exchange_ttl_seconds=int(os.getenv("GOOGLE_OAUTH_EXCHANGE_TTL_SECONDS", "120")),
            guest_user_ttl_days=int(os.getenv("GUEST_USER_TTL_DAYS", "7")),
            google_oauth_redirect_targets=google_redirect_targets,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
