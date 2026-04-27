from __future__ import annotations

import json
import os
from typing import Any

import redis


def _build_client() -> redis.Redis | None:
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT")
    if not host or not port:
        return None
    return redis.Redis(
        host=host,
        port=int(port),
        username=os.getenv("REDIS_USERNAME"),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True,
    )


cache_db = _build_client()


def cache_get_json(key: str) -> Any | None:
    if cache_db is None:
        return None
    raw_value = cache_db.get(key)
    if raw_value is None:
        return None
    return json.loads(raw_value)


def cache_set_json(key: str, value: Any, ttl_seconds: int = 60) -> None:
    if cache_db is None:
        return
    cache_db.set(key, json.dumps(value), ex=ttl_seconds)


def cache_delete(key: str) -> None:
    if cache_db is None:
        return
    cache_db.delete(key)
