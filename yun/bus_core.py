from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

YUN_JSON = DATA_DIR / "yun.json"
ALIASES_JSON = DATA_DIR / "aliases.json"

DEFAULT_ORIGIN = "斗六火車站"
DEFAULT_RETURN_DEST = "斗六火車站"


# -----------------------------
# 基本工具
# -----------------------------
def current_datetime_taipei() -> datetime:
    try:
        return datetime.now(ZoneInfo("Asia/Taipei"))
    except Exception:
        return datetime.now()


def current_time_str() -> str:
    return current_datetime_taipei().strftime("%H:%M")


def hhmm_to_minutes(hhmm: str) -> int:
    dt = datetime.strptime(hhmm, "%H:%M")
    return dt.hour * 60 + dt.minute


def minutes_to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases() -> dict[str, str]:
    raw = load_json(ALIASES_JSON)
    alias_map = {}
    for canonical, aliases in raw.items():
        alias_map[normalize_text(canonical)] = canonical
        if isinstance(aliases, list):
            for alias in aliases:
                alias_map[normalize_text(alias)] = canonical
    return alias_map


ALIAS_MAP = load_aliases()


def canonicalize_place(name: str) -> str:
    return ALIAS_MAP.get(normalize_text(name), name.strip())


# -----------------------------
# 數字 / 時間轉換
# -----------------------------
CH_NUM_MAP = {
    "零": "0", "〇": "0",
    "一": "1", "二": "2", "兩": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
}


def normalize_chinese_route_numbers(text: str) -> str:
    def repl(match):
        s = match.group(0)
        return "".join(CH_NUM_MAP.get(ch, ch) for ch in s)
    return re.sub(r"[零〇一二兩三四五六七八九]{2,4}", repl, text)


def zh_num_to_int(s: str) -> Optional[int]:
    zh_map = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10
    }

    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10

    if "十" in s:
        parts = s.split("十")
        tens = 1 if parts[0] == "" else zh_map.get(parts[0])
        if tens is None:
            return None
        ones = 0
        if len(parts) > 1 and parts[1] != "":
            ones = zh_map.get(parts[1])
            if ones is None:
                return None
        return tens * 10 + ones

    total = 0
    for ch in s:
        if ch not in zh_map:
            return None
        total = total * 10 + zh_map[ch]
    return total


def chinese_time_phrase_to_hhmm(text: str) -> Optional[str]:
    text = text.strip()

    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    m = re.search(
        r"(凌晨|早上|上午|中午|下午|晚上|傍晚)?"
        r"([零〇一二兩三四五六七八九十\d]{1,3})點"
        r"([零〇一二兩三四五六七八九十\d]{1,2}分|半)?",
        text
    )
    if not m:
        return None

    period = m.group(1)
    hour = zh_num_to_int(m.group(2))
    if hour is None:
        return None

    minute_raw = m.group(3)
    if minute_raw is None:
        minute = 0
    elif minute_raw == "半":
        minute = 30
    else:
        minute = zh_num_to_int(minute_raw.replace("分", ""))
        if minute is None:
            return None

    if period in {"下午", "晚上", "傍晚"} and 1 <= hour <= 11:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def number_to_chinese(n: int) -> str:
    nums = "零一二三四五六七八九"
    if n < 10:
        return nums[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + nums[n % 10]
    if n % 10 == 0:
        return nums[n // 10] + "十"
    return nums[n // 10] + "十" + nums[n % 10]


def route_number_to_chinese(route: str) -> str:
    digit_map = "零一二三四五六七八九"
    result = ""
    for ch in route:
        if ch.isdigit():
            result += digit_map[int(ch)]
        else:
            result += ch
    return result


def time_to_chinese(time_str: str) -> str:
    try:
        h, m = map(int, time_str.split(":"))
        h_str = number_to_chinese(h)
        if m == 0:
            return f"{h_str}點整"
        if m < 10:
            return f"{h_str}點零{number_to_chinese(m)}分"
        return f"{h_str}點{number_to_chinese(m)}分"
    except Exception:
        return time_str


def convert_output_text(text: str) -> str:
    text = re.sub(r"\b\d{2}:\d{2}\b", lambda m: time_to_chinese(m.group(0)), text)
    return text


# -----------------------------
# 時間條件解析
# -----------------------------
TIME_PERIODS = {
    "凌晨": ("00:00", "05:59"),
    "早上": ("06:00", "11:59"),
    "上午": ("06:00", "11:59"),
    "中午": ("11:00", "13:00"),
    "下午": ("12:00", "17:59"),
    "傍晚": ("17:00", "18:59"),
    "晚上": ("18:00", "23:59"),
}


def parse_relative_after(question: str, now_dt: datetime) -> Optional[str]:
    q = normalize_chinese_route_numbers(question)

    m = re.search(r"(\d+)\s*分鐘後", q)
    if m:
        return (now_dt + timedelta(minutes=int(m.group(1)))).strftime("%H:%M")

    m = re.search(r"([零〇一二兩三四五六七八九十]+)\s*分鐘後", q)
    if m:
        n = zh_num_to_int(m.group(1))
        if n is not None:
            return (now_dt + timedelta(minutes=n)).strftime("%H:%M")

    if "半小時後" in q:
        return (now_dt + timedelta(minutes=30)).strftime("%H:%M")

    m = re.search(r"(\d+)\s*小時後", q)
    if m:
        return (now_dt + timedelta(hours=int(m.group(1)))).strftime("%H:%M")

    m = re.search(r"([零〇一二兩三四五六七八九十]+)\s*小時後", q)
    if m:
        n = zh_num_to_int(m.group(1))
        if n is not None:
            return (now_dt + timedelta(hours=n)).strftime("%H:%M")

    return None


def parse_explicit_after(question: str) -> Optional[str]:
    m = re.search(
        r"((?:\d{1,2}:\d{2})|(?:凌晨|早上|上午|中午|下午|晚上|傍晚)?[零〇一二兩三四五六七八九十\d]{1,3}點(?:半|[零〇一二兩三四五六七八九十\d]{1,2}分)?))\s*(以後|之後|後)",
        question
    )
    if m:
        return chinese_time_phrase_to_hhmm(m.group(1))
    return None


def parse_explicit_before(question: str) -> Optional[str]:
    m = re.search(
        r"((?:\d{1,2}:\d{2})|(?:凌晨|早上|上午|中午|下午|晚上|傍晚)?[零〇一二兩三四五六七八九十\d]{1,3}點(?:半|[零〇一二兩三四五六七八九十\d]{1,2}分)?))\s*前",
        question
    )
    if m:
        return chinese_time_phrase_to_hhmm(m.group(1))
    return None


def parse_period_range(question: str) -> Optional[tuple[str, str, str]]:
    for label, (start, end) in TIME_PERIODS.items():
        if label in question:
            return label, start, end
    return None


def extract_time_constraints(question: str, now_dt: datetime) -> dict[str, Any]:
    explicit_after = parse_explicit_after(question)
    explicit_before = parse_explicit_before(question)
    relative_after = parse_relative_after(question, now_dt)
    period_range = parse_period_range(question)

    result = {
        "after": None,
        "before": None,
        "period_range": None,
        "time_label": None,
    }

    if explicit_after:
        result["after"] = explicit_after
    elif relative_after:
        result["after"] = relative_after

    if explicit_before:
        result["before"] = explicit_before

    if period_range:
        label, start, end = period_range
        result["period_range"] = period_range
        result["time_label"] = label
        if result["after"] is None:
            result["after"] = start

    return result


# -----------------------------
# 載入路線資料
# -----------------------------
def load_routes() -> dict:
    raw = load_json(YUN_JSON)
    return raw.get("routes", raw)


def route_exists(routes: dict, route_name: str) -> bool:
    return route_name in routes


def get_route_directions(routes: dict, route_name: str) -> dict:
    if not route_exists(routes, route_name):
        return {}
    return routes[route_name].get("directions", {})


def get_all_stops(routes: dict) -> set[str]:
    stops = set()
    for route_data in routes.values():
        for direction_data in route_data.get("directions", {}).values():
            for stop in direction_data.get("stops", []):
                stops.add(stop)
    return stops


def stop_exists(routes: dict, stop_name: str) -> bool:
    return canonicalize_place(stop_name) in get_all_stops(routes)


# -----------------------------
# 站牌 / 路線查詢
# -----------------------------
def find_stop_times_in_route(routes: dict, route_name: str, stop_name: str) -> list[dict]:
    stop_name = canonicalize_place(stop_name)
    result = []

    for direction_key, direction_data in get_route_directions(routes, route_name).items():
        for trip in direction_data.get("trips", []):
            time_str = trip.get("times_by_stop", {}).get(stop_name)
            if time_str:
                result.append(
                    {
                        "route_name": route_name,
                        "direction": direction_key,
                        "trip_no": trip["trip_no"],
                        "time": time_str,
                        "start_time": trip["start_time"],
                        "end_time": trip["end_time"],
                    }
                )

    result.sort(key=lambda x: hhmm_to_minutes(x["time"]))
    return result


def find_stop_all_routes(routes: dict, stop_name: str) -> list[dict]:
    stop_name = canonicalize_place(stop_name)
    result = []

    for route_name in routes.keys():
        result.extend(find_stop_times_in_route(routes, route_name, stop_name))

    result.sort(key=lambda x: hhmm_to_minutes(x["time"]))
    return result


def filter_by_after(items: list[dict], key: str, after: Optional[str]) -> list[dict]:
    if not after:
        return items
    after_m = hhmm_to_minutes(after)
    return [x for x in items if hhmm_to_minutes(x[key]) >= after_m]


def filter_by_before(items: list[dict], key: str, before: Optional[str]) -> list[dict]:
    if not before:
        return items
    before_m = hhmm_to_minutes(before)
    return [x for x in items if hhmm_to_minutes(x[key]) <= before_m]


def filter_by_period(items: list[dict], key: str, period_range: Optional[tuple[str, str, str]]) -> list[dict]:
    if not period_range:
        return items
    _, start, end = period_range
    start_m = hhmm_to_minutes(start)
    end_m = hhmm_to_minutes(end)
    return [x for x in items if start_m <= hhmm_to_minutes(x[key]) <= end_m]


# -----------------------------
# 對外核心查詢函式
# -----------------------------
def answer_route_schedule(
    routes: dict,
    route_name: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range=None,
) -> tuple[str, list[dict]]:
    if not route_exists(routes, route_name):
        return f"找不到路線 {route_name}。", []

    route_name_zh = route_number_to_chinese(route_name)
    lines = []
    directions = get_route_directions(routes, route_name)
    result_rows = []

    if period_range:
        lines.append(f"{route_name_zh} 在{period_range[0]}的班次如下：")
    elif after and before:
        lines.append(f"{route_name_zh} 在 {after} 到 {before} 之間的班次如下：")
    elif after:
        lines.append(f"{route_name_zh} 在 {after} 之後的班次如下：")
    elif before:
        lines.append(f"{route_name_zh} 在 {before} 之前的班次如下：")
    else:
        lines.append(f"{route_name_zh} 的班次如下：")

    found_any = False

    for direction_key, direction_data in directions.items():
        rows = []
        for trip in direction_data.get("trips", []):
            row = {
                "trip_no": trip["trip_no"],
                "start_time": trip["start_time"],
                "end_time": trip["end_time"],
                "direction": direction_key,
                "route_name": route_name,
            }
            rows.append(row)

        rows = filter_by_after(rows, "start_time", after if period_range is None else None)
        rows = filter_by_before(rows, "start_time", before if period_range is None else None)
        rows = filter_by_period(rows, "start_time", period_range)

        if not rows:
            continue

        found_any = True
        lines.append(f"方向是 {direction_key}。")
        for item in rows:
            result_rows.append(item)
            lines.append(
                f"第 {item['trip_no']} 班，於 {item['start_time']} 發車，於 {item['end_time']} 抵達。"
            )

    result_rows.sort(key=lambda x: hhmm_to_minutes(x["start_time"]))

    if not found_any:
        if period_range:
            return f"{route_name_zh} 在{period_range[0]}沒有班次。", []
        if after:
            return f"{route_name_zh} 在 {after} 之後沒有班次，今天的末班車可能已經過了。", []
        if before:
            return f"{route_name_zh} 在 {before} 之前沒有班次。", []
        return f"{route_name_zh} 目前查無班次資料。", []

    return "\n".join(lines), result_rows


def answer_stop_upcoming(
    routes: dict,
    stop_name: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range=None,
) -> tuple[str, list[dict]]:
    stop_name = canonicalize_place(stop_name)
    if not stop_exists(routes, stop_name):
        return f"找不到站名 {stop_name}。", []

    rows = find_stop_all_routes(routes, stop_name)
    rows = filter_by_after(rows, "time", after if period_range is None else None)
    rows = filter_by_before(rows, "time", before if period_range is None else None)
    rows = filter_by_period(rows, "time", period_range)

    if not rows:
        if period_range:
            return f"{stop_name} 在{period_range[0]}沒有班次。", []
        if after:
            return f"{stop_name} 在 {after} 之後沒有班次，今天的末班車可能已經過了。", []
        if before:
            return f"{stop_name} 在 {before} 之前沒有班次。", []
        return f"{stop_name} 目前查無班次資料。", []

    if period_range:
        lines = [f"{stop_name} 在{period_range[0]}還有以下班次："]
    elif after and before:
        lines = [f"{stop_name} 在 {after} 到 {before} 之間還有以下班次："]
    elif after:
        lines = [f"{stop_name} 在 {after} 之後還有以下班次："]
    elif before:
        lines = [f"{stop_name} 在 {before} 之前有以下班次："]
    else:
        lines = [f"{stop_name} 的班次如下："]

    for row in rows:
        lines.append(
            f"{row['time']}，路線 {route_number_to_chinese(row['route_name'])}，方向是 {row['direction']}。"
        )

    return "\n".join(lines), rows


def answer_stop_next_bus(
    routes: dict,
    stop_name: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range=None,
) -> tuple[str, list[dict]]:
    stop_name = canonicalize_place(stop_name)
    if not stop_exists(routes, stop_name):
        return f"找不到站名 {stop_name}。", []

    effective_after = after or current_time_str()
    all_rows = find_stop_all_routes(routes, stop_name)

    future_rows = filter_by_after(all_rows, "time", effective_after if period_range is None else None)
    future_rows = filter_by_before(future_rows, "time", before if period_range is None else None)
    future_rows = filter_by_period(future_rows, "time", period_range)

    if future_rows:
        next_row = future_rows[0]
        route_zh = route_number_to_chinese(next_row["route_name"])
        answer = (
            f"{stop_name} 下一班來的車是 "
            f"{route_zh}，"
            f"於 {next_row['time']} 抵達，"
            f"方向是 {next_row['direction']}。"
        )
        return answer, [next_row]

    if period_range:
        return f"{stop_name} 在{period_range[0]}沒有班次。", []

    if before:
        return f"{stop_name} 在 {before} 之前沒有符合的班次。", []

    if all_rows:
        next_day_first = all_rows[0]
        route_zh = route_number_to_chinese(next_day_first["route_name"])
        answer = (
            f"{stop_name} 今天的末班車已過。"
            f"明天最早一班是 {route_zh}，"
            f"於 {next_day_first['time']} 抵達，"
            f"方向是 {next_day_first['direction']}。"
        )
        return answer, [next_day_first]

    return f"{stop_name} 目前查無班次資料。", []


def answer_route_reach(
    routes: dict,
    route_name: str,
    destination: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range=None,
) -> tuple[str, list[dict]]:
    destination = canonicalize_place(destination)
    route_name_zh = route_number_to_chinese(route_name)
    rows = find_stop_times_in_route(routes, route_name, destination)

    if not rows:
        return f"{route_name_zh} 沒有到 {destination}。", []

    rows = filter_by_after(rows, "time", after if period_range is None else None)
    rows = filter_by_before(rows, "time", before if period_range is None else None)
    rows = filter_by_period(rows, "time", period_range)

    if not rows:
        if period_range:
            return f"{route_name_zh} 在{period_range[0]}沒有到 {destination} 的班次。", []
        if after:
            return f"{route_name_zh} 在 {after} 之後沒有到 {destination} 的班次。", []
        if before:
            return f"{route_name_zh} 在 {before} 之前沒有到 {destination} 的班次。", []
        return f"{route_name_zh} 目前查無到 {destination} 的班次。", []

    if period_range:
        lines = [f"{route_name_zh} 在{period_range[0]}有到 {destination}，可搭乘的班次如下："]
    elif after and before:
        lines = [f"{route_name_zh} 在 {after} 到 {before} 之間有到 {destination}，可搭乘的班次如下："]
    elif after:
        lines = [f"{route_name_zh} 在 {after} 之後有到 {destination}，可搭乘的班次如下："]
    elif before:
        lines = [f"{route_name_zh} 在 {before} 之前有到 {destination}，可搭乘的班次如下："]
    else:
        lines = [f"{route_name_zh} 有到 {destination}，可搭乘的班次如下："]

    for row in rows:
        lines.append(f"{row['time']}，方向是 {row['direction']}。")
    return "\n".join(lines), rows


def answer_route_reach_next(
    routes: dict,
    route_name: str,
    destination: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    period_range=None,
) -> tuple[str, list[dict]]:
    destination = canonicalize_place(destination)
    route_name_zh = route_number_to_chinese(route_name)

    all_rows = find_stop_times_in_route(routes, route_name, destination)
    if not all_rows:
        return f"{route_name_zh} 沒有到 {destination}。", []

    effective_after = after or current_time_str()

    future_rows = filter_by_after(all_rows, "time", effective_after if period_range is None else None)
    future_rows = filter_by_before(future_rows, "time", before if period_range is None else None)
    future_rows = filter_by_period(future_rows, "time", period_range)

    if future_rows:
        next_row = future_rows[0]
        answer = (
            f"{route_name_zh} 有到 {destination}。"
            f"最近一班是 {next_row['time']}，"
            f"方向是 {next_row['direction']}。"
        )
        return answer, [next_row]

    if period_range:
        return f"{route_name_zh} 在{period_range[0]}沒有到 {destination} 的班次。", []

    if before:
        return f"{route_name_zh} 在 {before} 之前沒有到 {destination} 的班次。", []

    next_day_first = all_rows[0]
    answer = (
        f"{route_name_zh} 今天到 {destination} 的末班車已過。"
        f"明天最早一班是 {next_day_first['time']}，"
        f"方向是 {next_day_first['direction']}。"
    )
    return answer, [next_day_first]


def find_direct_options(routes: dict, origin: str, destination: str, after: Optional[str] = None) -> list[dict]:
    origin = canonicalize_place(origin)
    destination = canonicalize_place(destination)

    options = []
    for route_name, route_data in routes.items():
        for direction_key, direction_data in route_data.get("directions", {}).items():
            stops = direction_data.get("stops", [])
            if origin not in stops or destination not in stops:
                continue

            origin_idx = stops.index(origin)
            dest_idx = stops.index(destination)
            if origin_idx >= dest_idx:
                continue

            for trip in direction_data.get("trips", []):
                times = trip.get("times_by_stop", {})
                depart_time = times.get(origin)
                arrive_time = times.get(destination)
                if not depart_time or not arrive_time:
                    continue
                if after and hhmm_to_minutes(depart_time) < hhmm_to_minutes(after):
                    continue

                options.append(
                    {
                        "type": "direct",
                        "route_name": route_name,
                        "direction": direction_key,
                        "trip_no": trip["trip_no"],
                        "depart_time": depart_time,
                        "arrive_time": arrive_time,
                        "duration_min": hhmm_to_minutes(arrive_time) - hhmm_to_minutes(depart_time),
                    }
                )

    options.sort(key=lambda x: hhmm_to_minutes(x["depart_time"]))
    return options


def answer_route_plan(
    routes: dict,
    destination: str,
    origin: str = DEFAULT_ORIGIN,
    after: Optional[str] = None
) -> tuple[str, list[dict]]:
    origin = canonicalize_place(origin)
    destination = canonicalize_place(destination)

    all_plans = find_direct_options(routes, origin, destination, after=None)

    if not all_plans:
        return f"從 {origin} 到 {destination}，目前找不到合適的直達路線。", []

    effective_after = after or current_time_str()

    future_plans = [
        p for p in all_plans
        if hhmm_to_minutes(p["depart_time"]) >= hhmm_to_minutes(effective_after)
    ]

    if future_plans:
        best = future_plans[0]
        duration_zh = number_to_chinese(best["duration_min"])
        return (
            f"從 {origin} 到 {destination} 可以直達。"
            f"下一班請搭乘 {route_number_to_chinese(best['route_name'])}，"
            f"方向是 {best['direction']}，"
            f"於 {origin} {best['depart_time']} 上車，"
            f"預計 {best['arrive_time']} 抵達 {destination}，"
            f"車程約 {duration_zh} 分鐘。"
        ), [best]

    next_day_first = all_plans[0]
    duration_zh = number_to_chinese(next_day_first["duration_min"])
    return (
        f"從 {origin} 到 {destination} 今天的末班車已過。"
        f"明天最早一班可搭乘 {route_number_to_chinese(next_day_first['route_name'])}，"
        f"方向是 {next_day_first['direction']}，"
        f"於 {origin} {next_day_first['depart_time']} 上車，"
        f"預計 {next_day_first['arrive_time']} 抵達 {destination}，"
        f"車程約 {duration_zh} 分鐘。"
    ), [next_day_first]


def answer_return_plan(routes: dict, from_place: str, destination: str = DEFAULT_RETURN_DEST, after: Optional[str] = None) -> tuple[str, list[dict]]:
    return answer_route_plan(routes, destination=destination, origin=from_place, after=after)


def answer_travel_time(
    routes: dict,
    destination: str,
    origin: str = DEFAULT_ORIGIN,
    after: Optional[str] = None
) -> tuple[str, list[dict]]:
    origin = canonicalize_place(origin)
    destination = canonicalize_place(destination)

    all_plans = find_direct_options(routes, origin, destination, after=None)

    if not all_plans:
        return f"從 {origin} 到 {destination}，目前找不到直達路線，因此無法估算時間。", []

    effective_after = after or current_time_str()

    future_plans = [
        p for p in all_plans
        if hhmm_to_minutes(p["depart_time"]) >= hhmm_to_minutes(effective_after)
    ]

    if future_plans:
        best = future_plans[0]
        duration_zh = number_to_chinese(best["duration_min"])
        return (
            f"從 {origin} 到 {destination}，下一班可搭乘 "
            f"{route_number_to_chinese(best['route_name'])}，"
            f"方向是 {best['direction']}，"
            f"車程約 {duration_zh} 分鐘。"
        ), [best]

    next_day_first = all_plans[0]
    duration_zh = number_to_chinese(next_day_first["duration_min"])
    return (
        f"從 {origin} 到 {destination} 今天的末班車已過。"
        f"明天最早一班可搭乘 {route_number_to_chinese(next_day_first['route_name'])}，"
        f"方向是 {next_day_first['direction']}，"
        f"車程約 {duration_zh} 分鐘。"
    ), [next_day_first]


def answer_arrival_feasible(
    routes: dict,
    destination: str,
    origin: str = DEFAULT_ORIGIN,
    after: Optional[str] = None,
    arrive_by: Optional[str] = None,
) -> tuple[str, list[dict]]:
    origin = canonicalize_place(origin)
    destination = canonicalize_place(destination)

    if not arrive_by:
        return "請提供到達時間，格式需為 HH:MM，例如 09:00。", []

    effective_after = after or current_time_str()

    plans = find_direct_options(routes, origin, destination, effective_after)
    feasible = [p for p in plans if hhmm_to_minutes(p["arrive_time"]) <= hhmm_to_minutes(arrive_by)]

    if not feasible:
        all_plans = find_direct_options(routes, origin, destination, after=None)
        if all_plans:
            return f"從 {origin} 出發，以 {effective_after} 之後的班次來看，想在 {arrive_by} 前到達 {destination}，目前無法安排。", []
        return f"從 {origin} 到 {destination}，目前找不到直達路線。", []

    best = feasible[0]
    return (
        f"可以。從 {origin} 出發，搭乘 {route_number_to_chinese(best['route_name'])}，方向是 {best['direction']}，"
        f"{best['depart_time']} 上車，{best['arrive_time']} 可到達 {destination}。"
    ), [best]