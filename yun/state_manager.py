from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional


class ConversationStateManager:
    """
    第一版先使用 in-memory store。
    之後若要換成 Redis / DB，只要保留相同介面即可。
    """

    def __init__(self, expire_minutes: int = 10):
        self._store: dict[str, dict[str, Any]] = {}
        self.expire_minutes = expire_minutes

    def _now(self) -> datetime:
        return datetime.now()

    def _stamp(self, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["_updated_at"] = self._now().isoformat()
        return state

    def get(self, session_id: str) -> dict[str, Any]:
        state = self._store.get(session_id, {})
        if not state:
            return {}

        if self.is_expired(state):
            self.clear(session_id)
            return {}

        return state

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        self._store[session_id] = self._stamp(state)

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(session_id)
        current.update(updates)
        self.save(session_id, current)
        return current

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def is_expired(self, state: dict[str, Any]) -> bool:
        raw = state.get("_updated_at")
        if not raw:
            return False

        try:
            updated_at = datetime.fromisoformat(raw)
        except Exception:
            return False

        return self._now() - updated_at > timedelta(minutes=self.expire_minutes)

    def get_last_cursor(self, session_id: str) -> Optional[dict[str, Any]]:
        state = self.get(session_id)
        return state.get("last_cursor")

    def set_last_cursor(self, session_id: str, cursor: Optional[dict[str, Any]]) -> None:
        state = self.get(session_id)
        state["last_cursor"] = cursor
        self.save(session_id, state)

    def build_query_state(
        self,
        *,
        schema_dict: dict[str, Any],
        cursor: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        將本輪查詢的重要欄位保存，供之後 ask-more 或 follow-up 使用。
        """
        return {
            "last_intent": schema_dict.get("intent"),
            "origin": schema_dict.get("origin"),
            "destination": schema_dict.get("destination"),
            "route": schema_dict.get("route"),
            "stop": schema_dict.get("stop"),
            "after": schema_dict.get("after"),
            "before": schema_dict.get("before"),
            "arrive_by": schema_dict.get("arrive_by"),
            "period_range": schema_dict.get("period_range"),
            "last_cursor": cursor,
        }