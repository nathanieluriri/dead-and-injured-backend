from __future__ import annotations

import enum
import logging
from urllib.parse import urlencode

import resend

from core.config import get_settings
from email_templates.changing_password_template import generate_changing_password_email_from_template
from email_templates.new_sign_in import generate_new_signin_warning_email_from_template
from email_templates.otp_template import generate_login_otp_email_from_template

logger = logging.getLogger(__name__)


class EmailDispatch(str, enum.Enum):
    """Outcome of an enqueue_email call.

    QUEUED  — handed off to the broker; the worker will deliver.
    DELAYED — broker unreachable; we logged the failure and the caller
              should surface a degraded UX. Without an outbox sweeper
              (see todo.md), DELAYED currently means "lost."
    """

    QUEUED = "queued"
    DELAYED = "delayed"


def _build_link(base_url: str, token: str) -> str:
    return f"{base_url}?{urlencode({'token': token})}"


def _deliver(subject: str, receiver_email: str, html_body: str, plain_text: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Skipping email delivery because RESEND_API_KEY is not set")
        return

    resend.api_key = settings.resend_api_key
    response = resend.Emails.send(
        {
            "from": f"{settings.resend_from_name} <{settings.resend_from_email}>",
            "to": [receiver_email],
            "subject": subject,
            "html": html_body,
            "text": plain_text,
        }
    )
    logger.info("Resend email accepted: to=%s subject=%s response=%s", receiver_email, subject, response)


def send_new_signin_email(receiver_email: str, username: str) -> None:
    html_body = generate_new_signin_warning_email_from_template(
        username,
        "",
        "recently",
        "unknown",
        "unknown",
        "Dead & Injured sign in",
    )
    _deliver(
        subject="New sign in detected",
        receiver_email=receiver_email,
        html_body=html_body,
        plain_text=f"Hello {username}, we detected a new sign in to your Dead & Injured account.",
    )


def send_password_reset_email(receiver_email: str, username: str, token: str) -> None:
    settings = get_settings()
    reset_link = _build_link(settings.password_reset_url, token)
    html_body = generate_login_otp_email_from_template(otp_code=reset_link, user_email=receiver_email)
    _deliver(
        subject="Reset your password",
        receiver_email=receiver_email,
        html_body=html_body,
        plain_text=(
            f"Hello {username}, click the following link to reset your password "
            f"(valid for {settings.password_reset_ttl_minutes} minutes): {reset_link}"
        ),
    )


def send_email_verification_email(receiver_email: str, username: str, token: str) -> None:
    settings = get_settings()
    verify_link = _build_link(settings.email_verification_url, token)
    html_body = generate_changing_password_email_from_template(
        otp_code=verify_link,
        user_email=receiver_email,
        avatar_image_link="https://iili.io/3DBDnYg.png",
    )
    _deliver(
        subject="Verify your email",
        receiver_email=receiver_email,
        html_body=html_body,
        plain_text=(
            f"Hello {username}, verify your email by visiting "
            f"(valid for {settings.email_verification_ttl_minutes} minutes): {verify_link}"
        ),
    )


def dispatch_email(kind: str, payload: dict[str, str]) -> None:
    try:
        if kind == "new_signin":
            send_new_signin_email(
                receiver_email=payload["receiver_email"],
                username=payload.get("username", payload["receiver_email"]),
            )
            return
        if kind == "password_reset":
            send_password_reset_email(
                receiver_email=payload["receiver_email"],
                username=payload.get("username", payload["receiver_email"]),
                token=payload["token"],
            )
            return
        if kind == "verify_email":
            send_email_verification_email(
                receiver_email=payload["receiver_email"],
                username=payload.get("username", payload["receiver_email"]),
                token=payload["token"],
            )
            return
        raise ValueError(f"Unsupported email kind: {kind}")
    except Exception as err:
        logger.exception("Email dispatch failed: %s", err)
        raise


def enqueue_email(kind: str, payload: dict[str, str]) -> EmailDispatch:
    try:
        from core.background_task import send_email_task

        send_email_task.delay(kind, payload)
        return EmailDispatch.QUEUED
    except Exception:
        # Do not block the request thread by sending inline if the broker is
        # unavailable. Log loudly so ops can re-queue once the broker is back.
        logger.exception("Email broker unavailable; dropping email kind=%s", kind)
        return EmailDispatch.DELAYED
