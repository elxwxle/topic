from __future__ import annotations

import os
import time
from typing import Any, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
BASE_URL = "https://tdx.transportdata.tw/api/basic/v2"
CITY = "YunlinCounty"

_access_token: Optional[str] = None
_token_expire_time: float = 0
_cache: dict[str, tuple[float, Any]] = {}


def _get_cache(key: str, ttl_seconds: int) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None

    saved_time, data = item
    if time.time() - saved_time <= ttl_seconds:
        return data

    return None


def _set_cache(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


def get_access_token() -> str:
    global _access_token, _token_expire_time

    now = time.time()
    if _access_token and now < _token_expire_time:
        return _access_token

    if not TDX_CLIENT_ID or not TDX_CLIENT_SECRET:
        raise RuntimeError(
            "缺少 TDX_CLIENT_ID 或 TDX_CLIENT_SECRET，請確認 api/.env 是否設定完成。"
        )

    data = {
        "grant_type": "client_credentials",
        "client_id": TDX_CLIENT_ID,
        "client_secret": TDX_CLIENT_SECRET,
    }

    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()

    token_data = response.json()
    _access_token = token_data["access_token"]
    expires_in = int(token_data.get("expires_in", 3600))
    _token_expire_time = now + expires_in - 60

    return _access_token


def get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Accept": "application/json",
    }


def tdx_get(
    path: str,
    cache_key: Optional[str] = None,
    ttl_seconds: int = 20,
) -> Any:
    if cache_key:
        cached = _get_cache(cache_key, ttl_seconds)
        if cached is not None:
            return cached

    url = f"{BASE_URL}{path}"
    response = requests.get(url, headers=get_headers(), timeout=15)
    response.raise_for_status()

    data = response.json()

    if cache_key:
        _set_cache(cache_key, data)

    return data


def get_yunlin_routes() -> list[dict[str, Any]]:
    return tdx_get(
        f"/Bus/Route/City/{CITY}?$format=JSON",
        cache_key="yunlin_routes",
        ttl_seconds=3600,
    )


def get_yunlin_stop_of_route(route_name: str) -> list[dict[str, Any]]:
    route = quote(str(route_name), safe="")
    return tdx_get(
        f"/Bus/StopOfRoute/City/{CITY}/{route}?$format=JSON",
        cache_key=f"stop_of_route:{route_name}",
        ttl_seconds=3600,
    )


def get_yunlin_eta(route_name: Optional[str] = None) -> list[dict[str, Any]]:
    if route_name:
        route = quote(str(route_name), safe="")
        return tdx_get(
            f"/Bus/EstimatedTimeOfArrival/City/{CITY}/{route}?$format=JSON",
            cache_key=f"eta:{route_name}",
            ttl_seconds=20,
        )

    return tdx_get(
        f"/Bus/EstimatedTimeOfArrival/City/{CITY}?$format=JSON",
        cache_key="eta:all",
        ttl_seconds=20,
    )


def get_yunlin_realtime(route_name: Optional[str] = None) -> list[dict[str, Any]]:
    if route_name:
        route = quote(str(route_name), safe="")
        return tdx_get(
            f"/Bus/RealTimeByFrequency/Streaming/City/{CITY}/{route}?$format=JSON",
            cache_key=f"realtime:{route_name}",
            ttl_seconds=15,
        )

    return tdx_get(
        f"/Bus/RealTimeByFrequency/Streaming/City/{CITY}?$format=JSON",
        cache_key="realtime:all",
        ttl_seconds=15,
    )