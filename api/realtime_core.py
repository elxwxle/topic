from __future__ import annotations

import re
from typing import Any, Optional

from tdx_client import get_yunlin_eta, get_yunlin_realtime


REALTIME_KEYWORDS = [
    "現在",
    "即時",
    "多久到",
    "幾分鐘",
    "下一班",
    "最近一班",
    "最近",
    "到站",
    "還有車",
    "有沒有車",
    "在哪",
    "位置",
    "目前在哪",
    "車在哪",
]


POSITION_KEYWORDS = [
    "在哪",
    "位置",
    "目前在哪",
    "車在哪",
    "公車在哪",
]


def legacy_response(
    answer: str,
    items: Optional[list[dict[str, Any]]] = None,
    cursor: Any = None,
    has_more: bool = False,
    total_count: Optional[int] = None,
) -> dict[str, Any]:
    """
    統一回傳舊版 /ask 格式。
    不回傳 schema、source、is_realtime、realtime_mode 等 debug 欄位。
    """
    safe_items = items or []

    return {
        "answer": answer,
        "items": safe_items,
        "cursor": cursor,
        "has_more": has_more,
        "total_count": len(safe_items) if total_count is None else total_count,
    }


def is_realtime_question(question: str) -> bool:
    return any(keyword in question for keyword in REALTIME_KEYWORDS)


def is_position_question(question: str) -> bool:
    return any(keyword in question for keyword in POSITION_KEYWORDS)


def extract_route_from_question(question: str) -> Optional[str]:
    """
    從問題中抓路線號碼。
    """
    match = re.search(r"\b\d{2,5}\b", question)

    if match:
        return match.group(0)

    return None


def get_name(obj: dict[str, Any], key: str) -> str:
    """
    從 TDX 的多語系欄位取中文名稱。
    例如：
        item["RouteName"]["Zh_tw"]
        item["StopName"]["Zh_tw"]
    """
    value = obj.get(key, {})

    if isinstance(value, dict):
        return value.get("Zh_tw") or value.get("En") or ""

    return str(value or "")


def stop_status_text(status: Optional[int]) -> str:
    """
    TDX StopStatus 對應文字。
    """
    mapping = {
        0: "正常",
        1: "尚未發車",
        2: "交管不停靠",
        3: "末班車已過",
        4: "今日未營運",
    }

    return mapping.get(status, "目前沒有預估時間")


def simplify_eta_item(item: dict[str, Any]) -> dict[str, Any]:
    route_name = get_name(item, "RouteName")
    stop_name = get_name(item, "StopName")

    estimate_time = item.get("EstimateTime")
    stop_status = item.get("StopStatus")
    direction = item.get("Direction")

    if estimate_time is not None:
        seconds = int(estimate_time)
        minute = max(0, seconds // 60)

        if seconds <= 30:
            estimate_text = "即將到站"
        else:
            estimate_text = f"{minute} 分鐘後到站"
    else:
        estimate_text = stop_status_text(stop_status)

    return {
        "route": route_name,
        "stop": stop_name,
        "direction": direction,
        "estimate_time": estimate_time,
        "estimate_text": estimate_text,
        "stop_status": stop_status,
        "update_time": item.get("UpdateTime"),
    }


def infer_stop_from_question(
    question: str,
    eta_rows: list[dict[str, Any]],
) -> Optional[str]:
    """
    從 TDX 回傳的站名中，反查使用者問題有沒有提到某個站。

    例如：
        question = "701 斗六火車站現在多久到？"
        eta_rows 裡有 "斗六火車站"
        就回傳 "斗六火車站"
    """
    stop_names = []

    for item in eta_rows:
        stop_name = get_name(item, "StopName")

        if stop_name and stop_name not in stop_names:
            stop_names.append(stop_name)

    # 站名長的優先，避免短站名誤判
    stop_names.sort(key=len, reverse=True)

    for stop_name in stop_names:
        if stop_name in question:
            return stop_name

    return None


def filter_eta_items(
    data: list[dict[str, Any]],
    route: Optional[str] = None,
    stop: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = []

    for item in data:
        row = simplify_eta_item(item)

        if route and str(row["route"]) != str(route):
            continue

        if stop and stop not in row["stop"]:
            continue

        rows.append(row)

    def sort_key(row: dict[str, Any]) -> int:
        estimate_time = row.get("estimate_time")

        if estimate_time is None:
            return 999999

        return int(estimate_time)

    rows.sort(key=sort_key)

    return rows


def build_eta_answer(
    rows: list[dict[str, Any]],
    route: Optional[str],
    stop: Optional[str],
) -> str:
    """
    產生簡潔版回答文字，讓回覆看起來像以前的聊天回答。
    """
    if not rows:
        if route and stop:
            return f"目前查不到 {route} 在「{stop}」的即時到站資料。"

        if route:
            return f"目前查不到 {route} 的即時到站資料。"

        if stop:
            return f"目前查不到「{stop}」的即時到站資料。"

        return "目前查不到即時到站資料。"

    first = rows[0]

    if route and stop:
        answer = f"{route} 在「{stop}」目前{first['estimate_text']}。"

        if first.get("update_time"):
            answer += f" 資料更新時間：{first['update_time']}。"

        return answer

    if route and not stop:
        answer = (
            f"我可以查 {route} 的即時到站時間，但需要知道你要查哪一站。\n"
            f"你可以這樣問：{route} 斗六火車站現在多久到？"
        )

        return answer

    if stop and not route:
        answer = f"「{stop}」目前最近一班是 {first['route']}，{first['estimate_text']}。"

        if first.get("update_time"):
            answer += f" 資料更新時間：{first['update_time']}。"

        return answer

    answer = f"目前最近一班是 {first['route']}｜{first['stop']}，{first['estimate_text']}。"

    if first.get("update_time"):
        answer += f" 資料更新時間：{first['update_time']}。"

    return answer


def answer_realtime_eta_from_question(
    question: str,
    route: Optional[str] = None,
    stop: Optional[str] = None,
) -> dict[str, Any]:
    """
    根據使用者問題查即時到站時間，並回傳舊版格式。
    """
    data = get_yunlin_eta(route)

    if not stop:
        stop = infer_stop_from_question(question, data)

    rows = filter_eta_items(data, route=route, stop=stop)
    answer = build_eta_answer(rows, route=route, stop=stop)

    # 舊格式可以保留 items，但不要回傳太多，避免前端畫面爆掉
    display_items = rows[:10] if stop else []

    return legacy_response(
        answer=answer,
        items=display_items,
        cursor=None,
        has_more=False,
        total_count=len(rows),
    )


def simplify_realtime_item(item: dict[str, Any]) -> dict[str, Any]:
    route_name = get_name(item, "RouteName")
    position = item.get("BusPosition", {}) or {}

    return {
        "route": route_name,
        "plate": item.get("PlateNumb"),
        "direction": item.get("Direction"),
        "lat": position.get("PositionLat"),
        "lon": position.get("PositionLon"),
        "speed": item.get("Speed"),
        "update_time": item.get("UpdateTime"),
    }


def answer_realtime_position_from_question(
    question: str,
    route: Optional[str] = None,
) -> dict[str, Any]:
    """
    根據使用者問題查即時車輛位置，並回傳舊版格式。
    """
    data = get_yunlin_realtime(route)

    rows = [simplify_realtime_item(item) for item in data]

    if route:
        rows = [row for row in rows if str(row["route"]) == str(route)]

    if not rows:
        if route:
            answer = f"目前查不到 {route} 的即時車輛位置。"
        else:
            answer = "目前查不到雲林公車的即時車輛位置。"

        return legacy_response(
            answer=answer,
            items=[],
            cursor=None,
            has_more=False,
            total_count=0,
        )

    if route:
        answer = f"目前查到 {route} 有 {len(rows)} 台車輛位置資料。"
    else:
        answer = f"目前查到 {len(rows)} 台車輛位置資料。"

    first_rows = rows[:5]

    for idx, row in enumerate(first_rows, start=1):
        answer += (
            f"\n{idx}. {row['route']}｜車牌 {row['plate']}｜"
            f"方向 {row['direction']}｜座標 ({row['lat']}, {row['lon']})"
        )

    return legacy_response(
        answer=answer,
        items=first_rows,
        cursor=None,
        has_more=len(rows) > 5,
        total_count=len(rows),
    )