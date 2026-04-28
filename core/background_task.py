from __future__ import annotations

from celery import Celery

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dead_and_injured",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "expire-stale-games-every-minute": {
            "task": "core.background_task.expire_stale_games",
            "schedule": 60.0,
        }
    },
)


@celery_app.task(name="core.background_task.send_email_task")
def send_email_task(kind: str, payload: dict[str, str]) -> None:
    from services.email_service import dispatch_email

    dispatch_email(kind=kind, payload=payload)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery worker safely.

    asyncio.run() cannot be called from within a running event loop. Each
    invocation here creates a fresh loop, runs the coroutine to completion,
    and tears the loop down again so coroutines can rely on standard asyncio
    primitives without leaking state between tasks.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="core.background_task.expire_stale_games")
def expire_stale_games() -> int:
    from services.game_service import expire_stale_games_job

    return _run_async(expire_stale_games_job())


@celery_app.task(name="core.background_task.rebuild_leaderboard_task")
def rebuild_leaderboard_task(user_ids: list[str] | None = None) -> int:
    from services.leaderboard_service import rebuild_leaderboard

    return _run_async(rebuild_leaderboard(user_ids=user_ids))
