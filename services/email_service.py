from __future__ import annotations

import enum
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from urllib.parse import urlencode

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


def _smtp_settings() -> dict[str, str | int] | None:
    username = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    host = os.getenv("EMAIL_HOST")
    port = os.getenv("EMAIL_PORT")
    if not all([username, password, host, port]):
        return None
    return {
        "username": username,
        "password": password,
        "host": host,
        "port": int(port),
    }


def _send_html_email(
    sender_email: str,
    sender_display_name: str,
    receiver_email: str,
    subject: str,
    html_content: str,
    plain_text_content: str,
    smtp_server: str,
    smtp_port: int,
    smtp_login: str,
    smtp_password: str,
) -> None:
    formatted_from_address = formataddr((sender_display_name, sender_email))
    msg = MIMEMultipart("alternative")
    msg["From"] = formatted_from_address
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    server = None
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        elif smtp_port in (25, 587):
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            raise ValueError("Unsupported SMTP port. Use 465, 587, or 25.")

        server.login(smtp_login, smtp_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
    finally:
        if server:
            server.quit()


def _deliver(subject: str, receiver_email: str, html_body: str, plain_text: str) -> None:
    smtp = _smtp_settings()
    if smtp is None:
        logger.warning("Skipping email delivery because SMTP settings are incomplete")
        return

    _send_html_email(
        sender_email=str(smtp["username"]),
        sender_display_name="Dead & Injured",
        receiver_email=receiver_email,
        subject=subject,
        html_content=html_body,
        plain_text_content=plain_text,
        smtp_server=str(smtp["host"]),
        smtp_port=int(smtp["port"]),
        smtp_login=str(smtp["username"]),
        smtp_password=str(smtp["password"]),
    )


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
