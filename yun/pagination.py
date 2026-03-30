from __future__ import annotations

from typing import Any, Optional


DEFAULT_PAGE_SIZE = 3


def make_cursor(
    *,
    intent: str,
    route: Optional[str] = None,
    stop: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range: Optional[tuple[str, str, str]] = None,
    offset: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "route": route,
        "stop": stop,
        "origin": origin,
        "destination": destination,
        "after": after,
        "before": before,
        "period_range": period_range,
        "offset": offset,
        "page_size": page_size,
    }


def paginate_items(items: list[dict], offset: int = 0, page_size: int = DEFAULT_PAGE_SIZE) -> tuple[list[dict], int, bool]:
    sliced = items[offset: offset + page_size]
    next_offset = offset + len(sliced)
    has_more = next_offset < len(items)
    return sliced, next_offset, has_more