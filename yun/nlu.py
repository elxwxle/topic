from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

from llm_client import LLMClient


CH_NUM_MAP = {
    "零": "0", "〇": "0",
    "一": "1", "二": "2", "兩": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
}

ZH_NUM_MAP = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10
}

TIME_PERIODS = {
    "凌晨": ("00:00", "05:59"),
    "早上": ("06:00", "11:59"),
    "上午": ("06:00", "11:59"),
    "中午": ("11:00", "13:00"),
    "下午": ("12:00", "17:59"),
    "傍晚": ("17:00", "18:59"),
    "晚上": ("18:00", "23:59"),
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def clean_question(text: str) -> str:
    q = text.strip()
    for x in ["請問", "一下", "幫我", "可以", "想問", "想知道", "呢", "嗎", "呀", "喔"]:
        q = q.replace(x, "")
    q = q.replace("公車", " 公車 ")
    q = q.replace("我要知道", "")
    q = q.replace("告訴我", "")
    q = q.replace("查一下", "")
    return q.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def zh_num_to_int(s: str) -> Optional[int]:
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        parts = s.split("十")
        tens = 1 if parts[0] == "" else ZH_NUM_MAP.get(parts[0])
        if tens is None:
            return None
        ones = 0
        if len(parts) > 1 and parts[1] != "":
            ones = ZH_NUM_MAP.get(parts[1])
            if ones is None:
                return None
        return tens * 10 + ones

    total = 0
    for ch in s:
        if ch not in ZH_NUM_MAP:
            return None
        total = total * 10 + ZH_NUM_MAP[ch]
    return total


def normalize_chinese_route_numbers(text: str) -> str:
    def repl(match):
        s = match.group(0)
        return "".join(CH_NUM_MAP.get(ch, ch) for ch in s)
    return re.sub(r"[零〇一二兩三四五六七八九]{2,4}", repl, text)


def chinese_time_phrase_to_hhmm(text: str) -> Optional[str]:
    text = text.strip()

    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    m = re.search(
        r"(凌晨|早上|上午|中午|下午|晚上|傍晚)?"
        r"([零〇一二兩三四五六七八九十\d]{1,3})點"
        r"(半|[零〇一二兩三四五六七八九十\d]{1,2}分)?",
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


def parse_relative_after(question: str, now_dt: datetime) -> Optional[str]:
    q = question

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
    pattern = (
        r"((?:\d{1,2}:\d{2})|"
        r"(?:凌晨|早上|上午|中午|下午|晚上|傍晚)?"
        r"[零〇一二兩三四五六七八九十\d]{1,3}點"
        r"(?:半|[零〇一二兩三四五六七八九十\d]{1,2}分)?)"
        r"\s*(以後|之後|後)"
    )
    m = re.search(pattern, question)
    if m:
        return chinese_time_phrase_to_hhmm(m.group(1))
    return None


def parse_explicit_before(question: str) -> Optional[str]:
    pattern = (
        r"((?:\d{1,2}:\d{2})|"
        r"(?:凌晨|早上|上午|中午|下午|晚上|傍晚)?"
        r"[零〇一二兩三四五六七八九十\d]{1,3}點"
        r"(?:半|[零〇一二兩三四五六七八九十\d]{1,2}分)?)"
        r"\s*前"
    )
    m = re.search(pattern, question)
    if m:
        return chinese_time_phrase_to_hhmm(m.group(1))
    return None


def parse_period_range(question: str) -> Optional[tuple[str, str, str]]:
    for label, (start, end) in TIME_PERIODS.items():
        if label in question:
            return label, start, end
    return None


@dataclass
class NLUSchema:
    intent: str = "unknown"
    route: Optional[str] = None
    stop: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    after: Optional[str] = None
    before: Optional[str] = None
    arrive_by: Optional[str] = None
    period_label: Optional[str] = None
    period_range: Optional[tuple[str, str, str]] = None
    result_mode: str = "all"
    confidence: float = 0.0
    source: str = "rules"
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_alias_map(raw_aliases: dict[str, list[str]]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for canonical, aliases in raw_aliases.items():
        alias_map[normalize_text(canonical)] = canonical
        if isinstance(aliases, list):
            for alias in aliases:
                alias_map[normalize_text(alias)] = canonical
    return alias_map


def get_all_stops(routes: dict) -> list[str]:
    stops = set()
    for route_data in routes.values():
        for direction_data in route_data.get("directions", {}).values():
            for stop in direction_data.get("stops", []):
                stops.add(stop)
    return sorted(stops)


def extract_route_candidates(question: str, routes: dict) -> list[str]:
    found = []
    q = normalize_chinese_route_numbers(question)

    raw_candidates = re.findall(r"\b[A-Za-z]?\d{2,3}\b", q)
    for c in raw_candidates:
        if c in routes and c not in found:
            found.append(c)

    for r in routes.keys():
        if r in q and r not in found:
            found.append(r)

    return found


def extract_stop_candidates(question: str, routes: dict, alias_map: dict[str, str]) -> list[str]:
    q = normalize_text(question)
    all_stops = get_all_stops(routes)
    result = []

    for alias_norm, canonical in alias_map.items():
        if alias_norm and alias_norm in q and canonical not in result:
            result.append(canonical)

    for stop in all_stops:
        stop_norm = normalize_text(stop)
        if stop_norm and stop_norm in q and stop not in result:
            result.append(stop)

    if not result:
        q2 = re.sub(r"[，。！？,.? ]+", "", q)
        best_stop = None
        best_score = 0.0
        for stop in all_stops:
            score = similarity(q2, normalize_text(stop))
            if score > best_score:
                best_score = score
                best_stop = stop
        if best_stop and best_score >= 0.55:
            result.append(best_stop)

    return result


def extract_origin_destination(question: str, routes: dict, alias_map: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    q = question
    stop_candidates = extract_stop_candidates(q, routes, alias_map)

    origin = None
    destination = None

    m = re.search(r"從(.+?)到(.+)", q)
    if m:
        left = m.group(1).strip()
        right = m.group(2).strip()
        left_stops = extract_stop_candidates(left, routes, alias_map)
        right_stops = extract_stop_candidates(right, routes, alias_map)
        if left_stops:
            origin = left_stops[0]
        if right_stops:
            destination = right_stops[0]
        return origin, destination

    m = re.search(r"從(.+?)回(.+)", q)
    if m:
        left = m.group(1).strip()
        right = m.group(2).strip()
        left_stops = extract_stop_candidates(left, routes, alias_map)
        right_stops = extract_stop_candidates(right, routes, alias_map)
        if left_stops:
            origin = left_stops[0]
        if right_stops:
            destination = right_stops[0]
        return origin, destination

    m = re.search(r"(.+?)回(.+)", q)
    if m:
        left = m.group(1).strip()
        right = m.group(2).strip()
        left_stops = extract_stop_candidates(left, routes, alias_map)
        right_stops = extract_stop_candidates(right, routes, alias_map)
        if left_stops:
            origin = left_stops[0]
        if right_stops:
            destination = right_stops[0]
        return origin, destination

    for pat in [r"到(.+)", r"去(.+)"]:
        m = re.search(pat, q)
        if m:
            right = m.group(1).strip()
            right_stops = extract_stop_candidates(right, routes, alias_map)
            if right_stops:
                destination = right_stops[0]
                break

    if stop_candidates and destination is None:
        destination = stop_candidates[0]

    return origin, destination


def detect_intent(
    question: str,
    routes: dict,
    alias_map: dict[str, str],
) -> tuple[str, float, dict[str, float]]:
    q = question
    route_candidates = extract_route_candidates(q, routes)
    stop_candidates = extract_stop_candidates(q, routes, alias_map)

    score = {
        "route_plan": 0.0,
        "return_plan": 0.0,
        "travel_time": 0.0,
        "route_reach": 0.0,
        "route_schedule": 0.0,
        "stop_upcoming": 0.0,
        "arrival_feasible": 0.0,
    }

    if any(k in q for k in ["怎麼去", "怎麼搭", "如何到", "如何去", "怎麼走"]):
        score["route_plan"] += 3.0

    if "回" in q and any(k in q for k in ["怎麼搭", "怎麼回", "如何", "怎麼"]):
        score["return_plan"] += 3.5

    if any(k in q for k in ["多久", "多長時間", "要幾分鐘", "花多久", "要多久"]):
        score["travel_time"] += 3.0

    if "前" in q and any(k in q for k in [
        "能不能到", "可不可以到", "趕得到", "到得了",
        "來得及", "能到嗎", "到得及", "前到", "前抵達", "前到達"
    ]):
        score["arrival_feasible"] += 4.0

    if route_candidates and any(k in q for k in ["有沒有到", "會到", "有到", "能不能到", "會不會到", "有沒有經過", "會經過"]):
        score["route_reach"] += 3.5

    if route_candidates and any(k in q for k in ["幾點", "班次", "發車", "下一班", "末班", "最後一班", "還有車", "還有沒有車"]):
        score["route_schedule"] += 3.0

    if stop_candidates and any(k in q for k in ["有沒有車", "還有沒有車", "下一班", "末班車", "最後一班"]):
        score["stop_upcoming"] += 2.5

    if route_candidates and "什麼時候" in q:
        score["route_schedule"] += 1.8

    if stop_candidates and "什麼時候" in q:
        score["stop_upcoming"] += 1.0

    if "現在" in q or "接下來" in q or "今天" in q or "今晚" in q:
        score["route_schedule"] += 0.6
        score["stop_upcoming"] += 0.6

    if "從" in q and "到" in q and any(k in q for k in ["怎麼", "如何", "搭"]):
        score["route_plan"] += 2.2

    best_intent = max(score, key=score.get)
    best_score = score[best_intent]

    if best_score <= 0:
        return "unknown", 0.1, score

    conf = min(0.95, 0.45 + best_score / 10.0)
    return best_intent, conf, score


def parse_with_rules(
    question: str,
    routes: dict,
    raw_aliases: dict[str, list[str]],
    now_dt: Optional[datetime] = None,
) -> NLUSchema:
    now_dt = now_dt or datetime.now()
    alias_map = build_alias_map(raw_aliases)

    raw_q = question.strip()
    q = clean_question(normalize_chinese_route_numbers(raw_q))

    route_candidates = extract_route_candidates(q, routes)
    stop_candidates = extract_stop_candidates(q, routes, alias_map)
    origin, destination = extract_origin_destination(q, routes, alias_map)

    after = parse_explicit_after(q)
    before = parse_explicit_before(q)
    relative_after = parse_relative_after(q, now_dt)
    period_range = parse_period_range(q)
    period_label = period_range[0] if period_range else None

    if after is None and relative_after is not None:
        after = relative_after

    if period_range and after is None:
        after = period_range[1]

    if "現在" in q and after is None:
        after = now_dt.strftime("%H:%M")

    # 新規劃問題時，如果本句沒有明確指定路線，就不要保留 route
    explicit_route_in_text = any(r in q for r in routes.keys())
    if any(k in q for k in ["如何到", "如何去", "怎麼去", "怎麼搭", "怎麼走"]):
        if not explicit_route_in_text:
            route_candidates = []

    intent, confidence, score_detail = detect_intent(q, routes, alias_map)

    result_mode = "all"
    if any(k in q for k in ["下一班", "最近一班", "最近來的車", "最近可搭", "下一台"]):
        result_mode = "next"
    elif any(k in q for k in ["有到嗎", "會到嗎", "有沒有到", "會不會到"]):
        result_mode = "next"
    elif any(k in q for k in ["有沒有車", "還有沒有車"]) and (
        after is not None or before is not None or period_range is not None
    ):
        result_mode = "next"

    schema = NLUSchema(
        intent=intent,
        route=route_candidates[0] if route_candidates else None,
        stop=stop_candidates[0] if stop_candidates else None,
        origin=origin,
        destination=destination,
        after=after,
        before=before,
        arrive_by=before if intent == "arrival_feasible" else None,
        period_label=period_label,
        period_range=period_range,
        result_mode=result_mode,
        confidence=confidence,
        source="rules",
        debug={
            "raw_question": raw_q,
            "normalized_question": q,
            "route_candidates": route_candidates,
            "stop_candidates": stop_candidates,
            "intent_scores": score_detail,
        },
    )

    if schema.intent == "stop_upcoming" and schema.stop is None and stop_candidates:
        schema.stop = stop_candidates[0]

    if schema.intent in {"route_plan", "travel_time", "arrival_feasible"}:
        if schema.destination is None and stop_candidates:
            schema.destination = stop_candidates[0]

    if schema.intent == "return_plan":
        if schema.origin is None and stop_candidates:
            schema.origin = stop_candidates[0]
        if schema.destination is None and len(stop_candidates) >= 2:
            schema.destination = stop_candidates[1]

    return schema


def _default_unknown_schema() -> dict[str, Any]:
    return {
        "intent": "unknown",
        "route": None,
        "stop": None,
        "origin": None,
        "destination": None,
        "after": None,
        "before": None,
        "arrive_by": None,
        "period_label": None,
        "period_range": None,
        "result_mode": "all",
        "confidence": 0.0,
    }


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None

    candidate = m.group(0)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None

    return None


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def llm_extract_schema(question: str) -> dict[str, Any]:
    prompt = f"""
請將以下雲林公車使用者問題解析成 JSON。
只能輸出 JSON，不要輸出其他文字。

可用 intent:
- route_schedule
- stop_upcoming
- route_reach
- route_plan
- return_plan
- travel_time
- arrival_feasible
- unknown

欄位:
- intent
- route
- stop
- origin
- destination
- after
- before
- arrive_by
- period_label
- period_range
- result_mode
- confidence

規則:
1. 如果沒有值，請填 null。
2. confidence 請填 0 到 1 之間的小數。
3. period_range 若有值，格式要是 ["下午","12:00","17:59"] 這種陣列。
4. 只輸出一個 JSON 物件，不要加說明。
5. route 例如 "201"、"Y01"。
6. 若是「九點前能不能到雲科大」這類，intent 應為 arrival_feasible，arrive_by 應為 "09:00"。
7. 若是「如何到雲科」這類，intent 應為 route_plan。
8. result_mode 可用值為 "all" 或 "next"。
9. 若問題是「下一班」「最近一班」「有沒有到某地」這種，result_mode 應為 "next"。

使用者問題：
{question}
""".strip()

    def llm_extract_schema(question: str) -> dict[str, Any]:
    prompt = f"""
請將以下雲林公車使用者問題解析成 JSON。

只能輸出 JSON，不要輸出其他文字。

可用 intent:
- route_schedule
- stop_upcoming
- route_reach
- route_plan
- return_plan
- travel_time
- arrival_feasible
- unknown

欄位:
- intent
- route
- stop
- origin
- destination
- after
- before
- arrive_by
- period_label
- period_range
- result_mode
- confidence

規則:
1. 如果沒有值，請填 null。
2. confidence 請填 0 到 1 之間的小數。
3. period_range 若有值，格式要是 ["下午","12:00","17:59"] 這種陣列。
4. 只輸出一個 JSON 物件，不要加說明。
5. route 例如 "201"、"Y01"。
6. 若是「九點前能不能到雲科大」這類，intent 應為 arrival_feasible，arrive_by 應為 "09:00"。
7. 若是「如何到雲科」這類，intent 應為 route_plan。
8. result_mode 可用值為 "all" 或 "next"。
9. 若問題是「下一班」「最近一班」「有沒有到某地」這種，result_mode 應為 "next"。

使用者問題：
{question}
""".strip()

    try:
        text = get_llm_client().generate(prompt)
        obj = _extract_json_object(text)

        if not obj:
            return _default_unknown_schema()

        schema = _default_unknown_schema()
        schema.update(obj)

        if (
            schema.get("period_range")
            and isinstance(schema["period_range"], list)
            and len(schema["period_range"]) == 3
        ):
            schema["period_range"] = tuple(schema["period_range"])

        try:
            schema["confidence"] = float(schema.get("confidence", 0.0) or 0.0)
        except Exception:
            schema["confidence"] = 0.0

        return schema

    except Exception:
        return _default_unknown_schema()


LLMExtractor = Callable[[str], dict[str, Any]]


def safe_merge_schema(rule_schema: NLUSchema, llm_data: dict[str, Any]) -> NLUSchema:
    merged = NLUSchema(**rule_schema.to_dict())

    if not isinstance(llm_data, dict):
        return merged

    for key in [
        "intent", "route", "stop", "origin", "destination",
        "after", "before", "arrive_by", "period_label", "period_range",
        "result_mode"
    ]:
        val = llm_data.get(key)
        if val in [None, "", []]:
            continue

        # 新規劃問題時，如果原句沒有明確路線，不允許 LLM 硬補 route
        if key == "route":
            raw_q = rule_schema.debug.get("normalized_question", "")
            explicit_route_in_text = any(r in raw_q for r in [
                "Y01", "Y02", "Y03", "101", "102", "103",
                "201", "202", "203", "205", "301", "701"
            ])
            if any(k in raw_q for k in ["如何到", "如何去", "怎麼去", "怎麼搭", "怎麼走"]) and not explicit_route_in_text:
                continue

        current = getattr(merged, key)
        if current in [None, "", []] or merged.intent == "unknown":
            setattr(merged, key, val)

    if llm_data.get("confidence") is not None:
        try:
            merged.confidence = max(merged.confidence, float(llm_data["confidence"]))
        except Exception:
            pass

    merged.source = "rules+llm"
    merged.debug["llm_data"] = llm_data
    return merged


def parse_with_optional_llm(
    question: str,
    routes: dict,
    raw_aliases: dict[str, list[str]],
    llm_extractor: Optional[LLMExtractor] = None,
    now_dt: Optional[datetime] = None,
) -> NLUSchema:
    rule_schema = parse_with_rules(question, routes, raw_aliases, now_dt=now_dt)

    if llm_extractor is None:
        return rule_schema

    try:
        llm_data = llm_extractor(question)
        merged = safe_merge_schema(rule_schema, llm_data)
        return merged
    except Exception as e:
        rule_schema.debug["llm_error"] = str(e)
        return rule_schema


def schema_summary(schema: NLUSchema) -> str:
    return json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)