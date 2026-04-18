from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional


class ConversationStateManager:
    def __init__(self, store, expire_minutes: int = 10):
        self.store = store
        self.expire_minutes = expire_minutes
        self.expire_seconds = expire_minutes * 60

    def _now_iso(self) -> str:
        return datetime.now().isoformat()

    def _is_expired(self, state: dict) -> bool:
        updated_at = state.get("updated_at")
        if not updated_at:
            return False

        try:
            dt = datetime.fromisoformat(updated_at)
        except Exception:
            return False

        return datetime.now() > dt + timedelta(minutes=self.expire_minutes)

    def get_state(self, session_id: str) -> dict:
        state = self.store.get(session_id) or {}
        if state and self._is_expired(state):
            self.store.delete(session_id)
            return {}
        return state

    def save(self, session_id: str, state: dict) -> None:
        state = dict(state)
        state["updated_at"] = self._now_iso()
        self.store.set(session_id, state, self.expire_seconds)

    def clear(self, session_id: str) -> None:
        self.store.delete(session_id)

    def get_last_cursor(self, session_id: str) -> Optional[dict[str, Any]]:
        state = self.get_state(session_id)
        return state.get("last_cursor")

    def set_last_cursor(self, session_id: str, cursor: Optional[dict[str, Any]]) -> None:
        state = self.get_state(session_id)
        state["last_cursor"] = cursor
        self.save(session_id, state)

    def build_query_state(
        self,
        *,
        schema_dict: dict[str, Any],
        cursor: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "last_schema": schema_dict,
            "last_cursor": cursor,
        }