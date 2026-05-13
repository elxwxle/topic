from __future__ import annotations

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
]


def is_realtime_question(question: str) -> bool:
    return any(keyword in question for keyword in REALTIME_KEYWORDS)


def stop_status_text(status: Optional[int]) -> str:
    mapping = {
        0: "正常",
        1: "尚未發車",
        2: "交管不停靠",
        3: "末班車已過",
        4: "今日未營運",
    }
    return mapping.get(status, "目前沒有預估時間")


def get_name(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key, {})
    if isinstance(value, dict):
        return value.get("Zh_tw") or value.get("En") or ""
    return str(value or "")


def simplify_eta_item(item: dict[str, Any]) -> dict[str, Any]:
    route_name = get_name(item, "RouteName")
    stop_name = get_name(item, "StopName")

    estimate_time = item.get("EstimateTime")
    stop_status = item.get("StopStatus")
    direction = item.get("Direction")

    if estimate_time is not None:
        minute = max(0, int(estimate_time) // 60)
        estimate_text = f"{minute} 分鐘後到站"
    else:
        estimate_text = stop_status_text(stop_status)

    return {
        "source": "TDX",
        "type": "eta",
        "route": route_name,
        "stop": stop_name,
        "direction": direction,
        "estimate_time": estimate_time,
        "estimate_text": estimate_text,
        "stop_status": stop_status,
        "update_time": item.get("UpdateTime"),
    }


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

    def sort_key(row: dict[str, Any]):
        estimate_time = row.get("estimate_time")
        if estimate_time is None:
            return 999999
        return int(estimate_time)

    rows.sort(key=sort_key)
    return rows


def build_eta_answer(rows: list[dict[str, Any]], route: Optional[str], stop: Optional[str]) -> str:
    if not rows:
        if route and stop:
            return f"目前 TDX 查不到 {route} 在「{stop}」的即時到站資料。"
        if route:
            return f"目前 TDX 查不到 {route} 的即時到站資料。"
        if stop:
            return f"目前 TDX 查不到「{stop}」的即時到站資料。"
        return "目前 TDX 查不到即時到站資料。"

    first = rows[0]

    title_parts = []
    if route:
        title_parts.append(f"{route} 路線")
    if stop:
        title_parts.append(f"「{stop}」")

    title = " ".join(title_parts) if title_parts else "查詢結果"

    answer = f"{title}目前最近一班：{first['estimate_text']}。"

    if first.get("update_time"):
        answer += f"\n資料更新時間：{first['update_time']}。"

    answer += "\n\n以下是目前查到的即時到站資料："

    for idx, row in enumerate(rows[:5], start=1):
        answer += (
            f"\n{idx}. {row['route']}｜{row['stop']}｜"
            f"{row['estimate_text']}｜方向 {row['direction']}"
        )

    return answer


def answer_realtime_eta(
    *,
    route: Optional[str] = None,
    stop: Optional[str] = None,
) -> dict[str, Any]:
    data = get_yunlin_eta(route)
    rows = filter_eta_items(data, route=route, stop=stop)
    answer = build_eta_answer(rows, route=route, stop=stop)

    return {
        "answer": answer,
        "items": rows[:20],
        "cursor": None,
        "has_more": False,
        "total_count": len(rows),
        "source": "TDX",
        "is_realtime": True,
    }


def simplify_realtime_item(item: dict[str, Any]) -> dict[str, Any]:
    route_name = get_name(item, "RouteName")
    position = item.get("BusPosition", {}) or {}

    return {
        "source": "TDX",
        "type": "bus_position",
        "route": route_name,
        "plate": item.get("PlateNumb"),
        "direction": item.get("Direction"),
        "lat": position.get("PositionLat"),
        "lon": position.get("PositionLon"),
        "speed": item.get("Speed"),
        "update_time": item.get("UpdateTime"),
    }


def answer_realtime_position(route: Optional[str] = None) -> dict[str, Any]:
    data = get_yunlin_realtime(route)

    rows = [simplify_realtime_item(item) for item in data]

    if route:
        rows = [row for row in rows if str(row["route"]) == str(route)]

    if not rows:
        answer = f"目前 TDX 查不到 {route or '雲林公車'} 的即時車輛位置。"
    else:
        answer = f"目前查到 {len(rows)} 台車輛的即時位置。"
        for idx, row in enumerate(rows[:5], start=1):
            answer += (
                f"\n{idx}. {row['route']}｜車牌 {row['plate']}｜"
                f"方向 {row['direction']}｜座標 ({row['lat']}, {row['lon']})"
            )

    return {
        "answer": answer,
        "items": rows,
        "cursor": None,
        "has_more": False,
        "total_count": len(rows),
        "source": "TDX",
        "is_realtime": True,
    }