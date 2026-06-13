"""Pytest fixtures for the backend test-suite.

Tests run against an in-memory Mongo (``mongomock_motor``) so they need neither a
real database nor Redis/Celery. The Celery-backed ``core.background_task`` module
is stubbed before anything imports it, which also avoids pulling Celery/redis
config into the test process.
"""
from __future__ import annotations

import os
import sys
import types

os.environ.setdefault("DB_TYPE", "mongodb")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

# Stub the background-task module *before* any service imports it, so the win
# path's leaderboard enqueue is a no-op instead of trying to reach a broker.
_bg = types.ModuleType("core.background_task")


class _StubTask:
    def delay(self, *args, **kwargs):  # noqa: D401 - mimics Celery's .delay
        return None


_bg.rebuild_leaderboard_task = _StubTask()  # type: ignore[attr-defined]
sys.modules.setdefault("core.background_task", _bg)

import core.database  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

# Point the shared db handle at an in-memory mock. Services bind
# ``from core.database import db`` at import time, so this must happen before
# they are imported (which is the case: pytest loads conftest first).
core.database.db = AsyncMongoMockClient()["test"]

import pytest_asyncio  # noqa: E402

_COLLECTIONS = [
    "games",
    "players",
    "secrets",
    "matchs",
    "match_events",
    "match_modifiers",
    "scores",
    "wallets",
    "notifications",
    "presence",
    "leaderboards",
    "inventory",
    "matchmaking_queue",
    "users",
]


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Reset every collection between tests (same db object the services hold)."""
    for name in _COLLECTIONS:
        await core.database.db[name].delete_many({})
    yield
