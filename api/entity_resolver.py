from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ALIASES_JSON = DATA_DIR / "aliases.json"


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", "", str(text).strip())


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases_raw() -> dict:
    return load_json(ALIASES_JSON)


def build_alias_map(raw_aliases: dict[str, list[str] | str]) -> dict[str, str]:
    alias_map: dict[str, str] = {}

    for canonical, aliases in raw_aliases.items():
        alias_map[normalize_text(canonical)] = canonical

        if isinstance(aliases, list):
            for alias in aliases:
                alias_map[normalize_text(alias)] = canonical
        elif isinstance(aliases, str):
            alias_map[normalize_text(aliases)] = canonical

    return alias_map


ALIAS_MAP = build_alias_map(load_aliases_raw())


def canonicalize_place(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    return ALIAS_MAP.get(normalize_text(name), str(name).strip())


def get_all_stops(routes: dict) -> set[str]:
    stops = set()
    for route_data in routes.values():
        for direction_data in route_data.get("directions", {}).values():
            for stop in direction_data.get("stops", []):
                stops.add(stop)
    return stops


def resolve_place_if_exists(routes: dict, name: Optional[str]) -> Optional[str]:
    """
    先做 alias normalize，再檢查是否存在於 stops。
    若不在 stops 中，仍回傳 canonicalize 後名稱，讓上層決定要不要拒絕。
    """
    if not name:
        return name

    canonical = canonicalize_place(name)
    all_stops = get_all_stops(routes)

    if canonical in all_stops:
        return canonical

    return canonical


def resolve_schema_places(routes: dict, schema) -> None:
    """
    就地修改 schema 的常見地名欄位。
    """
    for key in ["origin", "destination", "stop"]:
        if hasattr(schema, key):
            value = getattr(schema, key)
            if value:
                setattr(schema, key, resolve_place_if_exists(routes, value))