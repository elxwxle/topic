import json
import os
import time
from typing import Optional

import redis


class MemoryStateStore:
    def __init__(self):
        self._data: dict[str, dict] = {}

    def get(self, session_id: str) -> Optional[dict]:
        item = self._data.get(session_id)
        if not item:
            return None

        expire_at = item.get("expire_at")
        if expire_at is not None and time.time() > expire_at:
            self._data.pop(session_id, None)
            return None

        return item.get("value")

    def set(self, session_id: str, value: dict, ttl_seconds: int) -> None:
        self._data[session_id] = {
            "value": value,
            "expire_at": time.time() + ttl_seconds if ttl_seconds > 0 else None,
        }

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class RedisStateStore:
    def __init__(self):
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD")

        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
        )

    def get(self, session_id: str) -> Optional[dict]:
        raw = self.client.get(session_id)
        if not raw:
            return None
        return json.loads(raw)

    def set(self, session_id: str, value: dict, ttl_seconds: int) -> None:
        self.client.set(session_id, json.dumps(value), ex=ttl_seconds)

    def delete(self, session_id: str) -> None:
        self.client.delete(session_id)


def create_state_store():
    backend = os.getenv("STATE_STORE_BACKEND", "memory").lower()

    if backend == "redis":
        return RedisStateStore()

    return MemoryStateStore()