from __future__ import annotations

from typing import Any, Optional


class ValidationError(Exception):
    pass


def validate_question(question: str) -> None:
    if question is None:
        raise ValidationError("question 不可為空。")
    if not isinstance(question, str):
        raise ValidationError("question 必須是字串。")
    if not question.strip():
        raise ValidationError("question 不可為空字串。")


def validate_session_id(session_id: Optional[str]) -> str:
    if session_id is None:
        return "default"
    if not isinstance(session_id, str):
        raise ValidationError("session_id 必須是字串。")
    session_id = session_id.strip()
    return session_id or "default"


def validate_cursor(cursor: Optional[dict[str, Any]]) -> None:
    if cursor is None:
        return
    if not isinstance(cursor, dict):
        raise ValidationError("cursor 必須是 dict。")

    if "offset" in cursor and not isinstance(cursor["offset"], int):
        raise ValidationError("cursor.offset 必須是整數。")

    if "page_size" in cursor and not isinstance(cursor["page_size"], int):
        raise ValidationError("cursor.page_size 必須是整數。")

    if "offset" in cursor and cursor["offset"] < 0:
        raise ValidationError("cursor.offset 不可小於 0。")

    if "page_size" in cursor and cursor["page_size"] <= 0:
        raise ValidationError("cursor.page_size 必須大於 0。")


def validate_schema_basic(schema) -> None:
    """
    只做最基本檢查，不碰業務細節。
    """
    if not hasattr(schema, "intent"):
        raise ValidationError("schema 缺少 intent 欄位。")

    if schema.intent == "route_schedule" and not getattr(schema, "route", None):
        raise ValidationError("route_schedule 缺少 route。")

    if schema.intent == "stop_upcoming" and not getattr(schema, "stop", None):
        raise ValidationError("stop_upcoming 缺少 stop。")

    if schema.intent == "route_reach":
        if not getattr(schema, "route", None):
            raise ValidationError("route_reach 缺少 route。")
        if not getattr(schema, "destination", None):
            raise ValidationError("route_reach 缺少 destination。")

    if schema.intent == "route_plan" and not getattr(schema, "destination", None):
        raise ValidationError("route_plan 缺少 destination。")

    if schema.intent == "return_plan" and not getattr(schema, "origin", None):
        raise ValidationError("return_plan 缺少 origin。")

    if schema.intent == "travel_time" and not getattr(schema, "destination", None):
        raise ValidationError("travel_time 缺少 destination。")

    if schema.intent == "arrival_feasible":
        if not getattr(schema, "destination", None):
            raise ValidationError("arrival_feasible 缺少 destination。")
        if not getattr(schema, "arrive_by", None):
            raise ValidationError("arrival_feasible 缺少 arrive_by。")