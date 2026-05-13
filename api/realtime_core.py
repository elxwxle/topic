from __future__ import annotations

import re
from typing import Any, Optional

from bus_core import (
    answer_stop_next_bus,
    current_time_str,
    find_stop_times_in_route,
    hhmm_to_minutes,
)
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
    "那",
    "呢",
]

POSITION_KEYWORDS = [
    "在哪",
    "位置",
    "目前在哪",
    "車在哪",
    "公車在哪",
]

NEXT_BUS_KEYWORDS = [
    "下一班",
    "下班",
    "再下一班",
    "後一班",
    "下一台",
    "下一輛",
]


CHINESE_DIGITS = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

CHINESE_ROUTE_DIGITS = {
    "零": "0",
    "〇": "0",
    "一": "1",
    "二": "2",
    "兩": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

SIMPLIFIED_TO_TRADITIONAL = {
    "分钟": "分鐘",
    "车辆": "車輛",
    "发车": "發車",
    "预计": "預計",
    "查询": "查詢",
    "资料": "資料",
    "车": "車",
    "县": "縣",
    "台": "臺",
}


def int_to_chinese_number(value: int) -> str:
    if value == 0:
        return "零"

    if value < 0:
        return "負" + int_to_chinese_number(abs(value))

    units = ["", "十", "百", "千"]
    digits = list(str(value))
    result: list[str] = []
    length = len(digits)

    for index, digit_char in enumerate(digits):
        digit = int(digit_char)
        position = length - index - 1

        if digit == 0:
            if result and result[-1] != "零":
                result.append("零")
        else:
            if digit == 1 and position == 1 and not result:
                result.append("十")
            else:
                result.append(CHINESE_DIGITS[digit_char] + units[position])

    text = "".join(result)
    return text.rstrip("零")


def digits_to_chinese_digits(text: str) -> str:
    return "".join(CHINESE_DIGITS.get(char, char) for char in str(text))


def chinese_route_to_digits(text: str) -> str:
    return "".join(CHINESE_ROUTE_DIGITS.get(char, char) for char in text)


def normalize_traditional_text(text: str) -> str:
    result = str(text)

    for simplified, traditional in SIMPLIFIED_TO_TRADITIONAL.items():
        result = result.replace(simplified, traditional)

    return result


def replace_remaining_digits(text: str) -> str:
    return re.sub(
        r"\d+",
        lambda match: digits_to_chinese_digits(match.group(0)),
        str(text),
    )


def normalize_answer_text(text: str) -> str:
    result = normalize_traditional_text(text)
    result = replace_remaining_digits(result)
    return result


def format_route_text(route: Optional[str]) -> str:
    if not route:
        return ""
    return f"路線{digits_to_chinese_digits(str(route))}"


def format_count_text(value: int, unit: str = "") -> str:
    return f"{int_to_chinese_number(value)}{unit}"


def format_eta_seconds(seconds: int) -> str:
    if seconds <= 30:
        return "即將到站"

    minutes = max(0, seconds // 60)

    if minutes <= 0:
        return "即將到站"

    return f"{int_to_chinese_number(minutes)}分鐘後到站"


def format_time_text(time_text: Optional[str]) -> str:
    if not time_text:
        return ""

    raw = str(time_text).strip()

    match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if not match:
        return replace_remaining_digits(raw)

    hour = int(match.group(1))
    minute = int(match.group(2))

    hour_text = int_to_chinese_number(hour)

    if minute == 0:
        return f"{hour_text}點整"

    if minute < 10:
        minute_text = "零" + int_to_chinese_number(minute)
    else:
        minute_text = int_to_chinese_number(minute)

    return f"{hour_text}點{minute_text}分"


def legacy_response(
    answer: str,
    items: Optional[list[dict[str, Any]]] = None,
    cursor: Any = None,
    has_more: bool = False,
    total_count: Optional[int] = None,
) -> dict[str, Any]:
    safe_items = items or []

    return {
        "answer": normalize_answer_text(answer),
        "items": safe_items,
        "cursor": cursor,
        "has_more": has_more,
        "total_count": len(safe_items) if total_count is None else total_count,
    }


def is_realtime_question(question: str) -> bool:
    return any(keyword in question for keyword in REALTIME_KEYWORDS)


def is_position_question(question: str) -> bool:
    return any(keyword in question for keyword in POSITION_KEYWORDS)


def is_next_bus_followup_question(question: str) -> bool:
    return any(keyword in question for keyword in NEXT_BUS_KEYWORDS)


def extract_route_from_question(question: str) -> Optional[str]:
    arabic_match = re.search(r"\b\d{2,5}\b", question)
    if arabic_match:
        return arabic_match.group(0)

    chinese_match = re.search(r"[零〇一二兩三四五六七八九]{2,5}", question)
    if chinese_match:
        return chinese_route_to_digits(chinese_match.group(0))

    return None


def get_name(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key, {})
    if isinstance(value, dict):
        return value.get("Zh_tw") or value.get("En") or ""
    return str(value or "")


def stop_status_text(status: Optional[int]) -> str:
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
        estimate_text = format_eta_seconds(int(estimate_time))
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
    stop_names: list[str] = []

    for item in eta_rows:
        stop_name = get_name(item, "StopName")
        if stop_name and stop_name not in stop_names:
            stop_names.append(stop_name)

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
    rows: list[dict[str, Any]] = []

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


def has_realtime_estimate(rows: list[dict[str, Any]]) -> bool:
    return bool(rows and rows[0].get("estimate_time") is not None)


def find_next_local_bus_for_route_stop(
    routes_data: dict,
    route: str,
    stop: str,
    after: Optional[str] = None,
    strict_after: bool = False,
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    rows = find_stop_times_in_route(routes_data, route, stop)

    if not rows:
        return None, None

    effective_after = after or current_time_str()
    after_min = hhmm_to_minutes(effective_after)

    if strict_after:
        future_rows = [
            row for row in rows
            if hhmm_to_minutes(row["time"]) > after_min
        ]
    else:
        future_rows = [
            row for row in rows
            if hhmm_to_minutes(row["time"]) >= after_min
        ]

    if future_rows:
        return "today", future_rows[0]

    return "tomorrow", rows[0]


def build_route_stop_local_fallback_text(
    routes_data: dict,
    route: str,
    stop: str,
    after: Optional[str] = None,
    strict_after: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    day_type, row = find_next_local_bus_for_route_stop(
        routes_data=routes_data,
        route=route,
        stop=stop,
        after=after,
        strict_after=strict_after,
    )

    if not row:
        return "本地班表也查不到這一站的最近班次。", []

    route_text = format_route_text(route)
    arrival_time = format_time_text(row.get("time"))
    start_time = format_time_text(row.get("start_time"))
    direction = row.get("direction", "未知方向")

    bus_label = "下一班" if strict_after else "最近一班"

    if day_type == "today":
        text = (
            f"根據班表，{route_text}{bus_label}預計{arrival_time}到「{stop}」，"
            f"發車時間是{start_time}，方向是{direction}。"
        )
    else:
        text = (
            "今天後面已經沒有符合條件的班次。"
            f"根據班表，明天最早一班{route_text}預計{arrival_time}到「{stop}」，"
            f"發車時間是{start_time}，方向是{direction}。"
        )

    return text, [row]


def build_stop_only_local_fallback_text(
    routes_data: dict,
    stop: str,
) -> tuple[str, list[dict[str, Any]]]:
    answer, rows = answer_stop_next_bus(
        routes=routes_data,
        stop_name=stop,
        after=current_time_str(),
    )

    return answer, rows


def build_eta_answer_with_local_fallback(
    *,
    routes_data: dict,
    rows: list[dict[str, Any]],
    route: Optional[str],
    stop: Optional[str],
    context_after_time: Optional[str] = None,
    strict_after: bool = False,
) -> dict[str, Any]:
    route_text = format_route_text(route)

    if route and not stop:
        return legacy_response(
            answer=(
                f"我可以查{route_text}的即時到站時間，"
                f"但需要知道你要查哪一站。"
                f"你可以問：{route_text}斗六火車站現在多久到？"
            ),
            items=[],
            cursor=None,
            has_more=False,
            total_count=len(rows),
        )

    if has_realtime_estimate(rows) and not strict_after:
        first = rows[0]
        first_route_text = format_route_text(first.get("route"))

        if route and stop:
            answer = f"{route_text}在「{stop}」目前{first['estimate_text']}。"
        elif stop:
            answer = f"「{stop}」目前最近一班是{first_route_text}，{first['estimate_text']}。"
        else:
            answer = (
                f"目前最近一班是{first_route_text}，"
                f"站牌是「{first['stop']}」，{first['estimate_text']}。"
            )

        answer += "資料已依即時到站資訊更新。"

        result = legacy_response(
            answer=answer,
            items=rows[:10],
            cursor=None,
            has_more=len(rows) > 10,
            total_count=len(rows),
        )

        result["_context"] = {
            "route": first.get("route") or route,
            "stop": first.get("stop") or stop,
            "mode": "eta",
            "last_answer_time": None,
        }
        return result

    if route and stop:
        if strict_after:
            tdx_status = "沿用上一題的路線與站牌。"
        else:
            tdx_status = "目前沒有即時預估資料"

            if rows:
                tdx_status = rows[0].get("estimate_text") or tdx_status

        fallback_text, fallback_rows = build_route_stop_local_fallback_text(
            routes_data=routes_data,
            route=route,
            stop=stop,
            after=context_after_time,
            strict_after=strict_after,
        )

        if strict_after:
            answer = f"{tdx_status}{fallback_text}"
        else:
            answer = f"{route_text}在「{stop}」{tdx_status}。{fallback_text}"

        last_answer_time = None
        if fallback_rows:
            last_answer_time = fallback_rows[0].get("time")

        result = legacy_response(
            answer=answer,
            items=fallback_rows,
            cursor=None,
            has_more=False,
            total_count=len(fallback_rows),
        )

        result["_context"] = {
            "route": route,
            "stop": stop,
            "mode": "eta",
            "last_answer_time": last_answer_time,
        }
        return result

    if stop and not route:
        fallback_text, fallback_rows = build_stop_only_local_fallback_text(
            routes_data=routes_data,
            stop=stop,
        )

        answer = f"目前即時資料沒有可用的到站預估。{fallback_text}"

        last_answer_time = None
        if fallback_rows:
            last_answer_time = fallback_rows[0].get("time")

        result = legacy_response(
            answer=answer,
            items=fallback_rows,
            cursor=None,
            has_more=False,
            total_count=len(fallback_rows),
        )

        result["_context"] = {
            "route": None,
            "stop": stop,
            "mode": "eta",
            "last_answer_time": last_answer_time,
        }
        return result

    return legacy_response(
        answer="目前查不到即時到站資料，請提供路線或站牌名稱。",
        items=[],
        cursor=None,
        has_more=False,
        total_count=0,
    )


def answer_realtime_eta_from_question(
    *,
    question: str,
    routes_data: dict,
    route: Optional[str] = None,
    stop: Optional[str] = None,
    context_route: Optional[str] = None,
    context_stop: Optional[str] = None,
    context_last_answer_time: Optional[str] = None,
) -> dict[str, Any]:
    route_use = route or context_route

    data = get_yunlin_eta(route_use)

    inferred_stop = infer_stop_from_question(question, data)
    stop_use = stop or inferred_stop or context_stop

    strict_after = is_next_bus_followup_question(question)

    if strict_after and route_use and stop_use and context_last_answer_time:
        return build_eta_answer_with_local_fallback(
            routes_data=routes_data,
            rows=[],
            route=route_use,
            stop=stop_use,
            context_after_time=context_last_answer_time,
            strict_after=True,
        )

    rows = filter_eta_items(data, route=route_use, stop=stop_use)

    return build_eta_answer_with_local_fallback(
        routes_data=routes_data,
        rows=rows,
        route=route_use,
        stop=stop_use,
        context_after_time=context_last_answer_time,
        strict_after=False,
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
    *,
    question: str,
    route: Optional[str] = None,
    context_route: Optional[str] = None,
) -> dict[str, Any]:
    route_use = route or context_route

    data = get_yunlin_realtime(route_use)
    rows = [simplify_realtime_item(item) for item in data]

    if route_use:
        rows = [row for row in rows if str(row["route"]) == str(route_use)]

    if not rows:
        if route_use:
            answer = f"目前查不到{format_route_text(route_use)}的即時車輛位置。"
        else:
            answer = "目前查不到雲林公車的即時車輛位置。"

        result = legacy_response(
            answer=answer,
            items=[],
            cursor=None,
            has_more=False,
            total_count=0,
        )

        result["_context"] = {
            "route": route_use,
            "stop": None,
            "mode": "position",
            "last_answer_time": None,
        }
        return result

    count_text = format_count_text(len(rows), "臺")

    if route_use:
        answer = f"目前查到{format_route_text(route_use)}有{count_text}車輛正在提供即時位置資料。"
    else:
        answer = f"目前查到雲林公車有{count_text}車輛正在提供即時位置資料。"

    answer += "詳細位置資料已放在下方資料列。"

    result = legacy_response(
        answer=answer,
        items=rows[:5],
        cursor=None,
        has_more=len(rows) > 5,
        total_count=len(rows),
    )

    result["_context"] = {
        "route": route_use,
        "stop": None,
        "mode": "position",
        "last_answer_time": None,
    }
    return result