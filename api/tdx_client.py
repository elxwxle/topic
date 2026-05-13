import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
BASE_URL = "https://tdx.transportdata.tw/api/basic/v2"

CITY = "YunlinCounty"

_access_token = None
_token_expire_time = 0


def get_access_token():
    """
    取得 TDX Access Token。
    做簡單快取，避免每次 API 都重新要 token。
    """
    global _access_token, _token_expire_time

    now = time.time()

    if _access_token and now < _token_expire_time:
        return _access_token

    if not TDX_CLIENT_ID or not TDX_CLIENT_SECRET:
        raise RuntimeError("缺少 TDX_CLIENT_ID 或 TDX_CLIENT_SECRET，請檢查 .env")

    data = {
        "grant_type": "client_credentials",
        "client_id": TDX_CLIENT_ID,
        "client_secret": TDX_CLIENT_SECRET,
    }

    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()

    token_data = response.json()

    _access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    # 提早 60 秒過期，避免剛好 token 失效
    _token_expire_time = now + expires_in - 60

    return _access_token


def get_headers():
    token = get_access_token()

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def get_yunlin_routes():
    """
    取得雲林所有公車路線。
    """
    url = f"{BASE_URL}/Bus/Route/City/{CITY}?$format=JSON"

    response = requests.get(url, headers=get_headers(), timeout=10)
    response.raise_for_status()

    return response.json()


def get_yunlin_stop_of_route(route_name: str):
    """
    取得某路線的站序。
    例如：701、7120。
    """
    url = f"{BASE_URL}/Bus/StopOfRoute/City/{CITY}/{route_name}?$format=JSON"

    response = requests.get(url, headers=get_headers(), timeout=10)
    response.raise_for_status()

    return response.json()


def get_yunlin_eta(route_name: str):
    """
    取得某路線的預估到站時間。
    EstimateTime 通常是秒數。
    """
    url = f"{BASE_URL}/Bus/EstimatedTimeOfArrival/City/{CITY}/{route_name}?$format=JSON"

    response = requests.get(url, headers=get_headers(), timeout=10)
    response.raise_for_status()

    return response.json()


def get_yunlin_realtime_by_frequency(route_name: str | None = None):
    """
    取得雲林公車即時位置/動態資料。
    route_name 可選。
    """
    if route_name:
        url = f"{BASE_URL}/Bus/RealTimeByFrequency/Streaming/City/{CITY}/{route_name}?$format=JSON"
    else:
        url = f"{BASE_URL}/Bus/RealTimeByFrequency/Streaming/City/{CITY}?$format=JSON"

    response = requests.get(url, headers=get_headers(), timeout=10)
    response.raise_for_status()

    return response.json()