import json
from typing import Optional

try:
    import redis
except Exception:
    redis = None


class MemoryStateStore:
    def __init__(self):
        self._data: dict[str, dict] = {}

    def get(self, session_id: str) -> Optional[dict]:
        return self._data.get(session_id)

    def set(self, session_id: str, value: dict, ttl_seconds: int) -> None:
        # 記憶體版先不做真正 TTL，交給 state_manager 控制
        self._data[session_id] = value

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class RedisStateStore:
    def __init__(self, url: str = "redis://localhost:6379/0", prefix: str = "yunbus:session:"):
        if redis is None:
            raise RuntimeError("redis 套件未安裝，請先 pip install redis")
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def get(self, session_id: str) -> Optional[dict]:
        raw = self.client.get(self._key(session_id))
        if not raw:
            return None
        return json.loads(raw)

    def set(self, session_id: str, value: dict, ttl_seconds: int) -> None:
        self.client.set(
            self._key(session_id),
            json.dumps(value, ensure_ascii=False),
            ex=ttl_seconds,
        )

    def delete(self, session_id: str) -> None:
        self.client.delete(self._key(session_id))