from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI
from pydantic import BaseModel

from bus_core import (
    load_routes,
    answer_route_schedule,
    answer_stop_upcoming,
    answer_stop_next_bus,
    answer_route_reach,
    answer_route_reach_next,
    answer_route_plan,
    answer_return_plan,
    answer_travel_time,
    answer_arrival_feasible,
    convert_output_text,
    route_number_to_chinese,
)
from nlu import (
    parse_with_optional_llm,
    llm_extract_schema,
)
from pagination import make_cursor, paginate_items
from state import conversation_state

try:
    from rag_core import rag_answer
except Exception:
    def rag_answer(query: str) -> str:
        return "目前找不到可補充的說明資料。"


# ---------------------------------
# 基本路徑設定
# ---------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ALIASES_JSON = DATA_DIR / "aliases.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases_raw() -> dict:
    return load_json(ALIASES_JSON)


# ---------------------------------
# FastAPI
# ---------------------------------
app = FastAPI(title="Yunlin Bus Assistant API")

routes_data = load_routes()
aliases_raw = load_aliases_raw()

conversation_state.setdefault("last_cursor", None)


# ---------------------------------
# Request Models
# ---------------------------------
class AskRequest(BaseModel):
    question: str


class ParseRequest(BaseModel):
    question: str


class AskMoreRequest(BaseModel):
    cursor: Optional[dict[str, Any]] = None


class RouteScheduleRequest(BaseModel):
    route: str
    after: Optional[str] = None
    before: Optional[str] = None


class StopUpcomingRequest(BaseModel):
    stop: str
    after: Optional[str] = None
    before: Optional[str] = None


class RouteReachRequest(BaseModel):
    route: str
    destination: str
    after: Optional[str] = None
    before: Optional[str] = None


class RoutePlanRequest(BaseModel):
    destination: str
    origin: str = "斗六火車站"
    after: Optional[str] = None


class ReturnPlanRequest(BaseModel):
    from_place: str
    destination: str = "斗六火車站"
    after: Optional[str] = None


class TravelTimeRequest(BaseModel):
    destination: str
    origin: str = "斗六火車站"
    after: Optional[str] = None


class ArrivalFeasibleRequest(BaseModel):
    destination: str
    origin: str = "斗六火車站"
    after: Optional[str] = None
    arrive_by: str


# ---------------------------------
# 單筆回答文字
# ---------------------------------
def build_single_item_answer(intent: str, page_items: list[dict], fallback_answer: str = "") -> str:
    if not page_items:
        return fallback_answer or "目前沒有資料。"

    item = page_items[0]
    route_zh = route_number_to_chinese(item["route_name"]) if "route_name" in item else ""

    if intent == "route_schedule":
        return (
            f"下一班是 {route_zh}，"
            f"方向是 {item['direction']}，"
            f"於 {item['start_time']} 發車，"
            f"於 {item['end_time']} 抵達。"
        )

    if intent == "stop_upcoming":
        if "time" in item:
            return (
                f"下一班來的車是 {route_zh}，"
                f"於 {item['time']} 抵達，"
                f"方向是 {item['direction']}。"
            )
        return fallback_answer or "目前沒有資料。"

    if intent == "route_reach":
        if "time" in item:
            start_text = f"{item['start_time']} 發車，" if "start_time" in item else ""
            return (
                f"最近一班可到達的班次是 {route_zh}，"
                f"{start_text}"
                f"{item['time']} 會到，"
                f"方向是 {item['direction']}。"
            )
        return fallback_answer or "目前沒有資料。"

    if intent == "route_plan":
        if "depart_time" in item and "arrive_time" in item:
            return (
                f"下一班可搭乘 {route_zh}，"
                f"方向是 {item['direction']}，"
                f"{item['depart_time']} 上車，"
                f"{item['arrive_time']} 抵達。"
            )
        return fallback_answer or "目前沒有資料。"

    if intent == "return_plan":
        if "depart_time" in item and "arrive_time" in item:
            return (
                f"下一班回程可搭乘 {route_zh}，"
                f"方向是 {item['direction']}，"
                f"{item['depart_time']} 上車，"
                f"{item['arrive_time']} 抵達。"
            )
        return fallback_answer or "目前沒有資料。"

    if intent == "travel_time":
        if "duration_min" in item:
            return (
                f"下一班可搭乘 {route_zh}，"
                f"方向是 {item['direction']}，"
                f"車程約 {item['duration_min']} 分鐘。"
            )
        return fallback_answer or "目前沒有資料。"

    if intent == "arrival_feasible":
        if "depart_time" in item and "arrive_time" in item:
            return (
                f"可以，搭乘 {route_zh}，"
                f"方向是 {item['direction']}，"
                f"{item['depart_time']} 上車，"
                f"{item['arrive_time']} 可到達。"
            )
        return fallback_answer or "目前沒有資料。"

    return fallback_answer or "查詢成功。"


# ---------------------------------
# 共用：把 rows 切成 page
# ---------------------------------
def build_paginated_response(
    *,
    answer: str,
    rows: list[dict],
    cursor: dict[str, Any],
    original_question: str = "",
):
    offset = cursor.get("offset", 0)
    page_size = cursor.get("page_size", 1)

    page_items, next_offset, has_more = paginate_items(
        rows,
        offset=offset,
        page_size=page_size,
    )

    next_cursor = dict(cursor)
    next_cursor["offset"] = next_offset
    next_cursor["page_size"] = page_size

    conversation_state["last_cursor"] = next_cursor if has_more else cursor

    single_answer = build_single_item_answer(
        cursor.get("intent", ""),
        page_items,
        fallback_answer=answer,
    )

    if not page_items and original_question:
        rag_text = rag_answer(original_question)
        if rag_text and rag_text != "目前找不到可補充的說明資料。":
            single_answer = f"{single_answer}\n\n{rag_text}"

    return {
        "answer": convert_output_text(single_answer),
        "items": page_items,
        "cursor": next_cursor,
        "has_more": has_more,
        "total_count": len(rows),
    }


# ---------------------------------
# 根據 schema 實際查詢
# ---------------------------------
def run_schema_query(schema):
    result_mode = getattr(schema, "result_mode", "all")
    raw_question = getattr(schema, "debug", {}).get("raw_question", "")

    if schema.intent == "route_schedule" and schema.route:
        answer, rows = answer_route_schedule(
            routes_data,
            schema.route,
            schema.after,
            schema.before,
            schema.period_range,
        )
        cursor = make_cursor(
            intent="route_schedule",
            route=schema.route,
            after=schema.after,
            before=schema.before,
            period_range=schema.period_range,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "stop_upcoming" and schema.stop:
        if result_mode == "next":
            answer, rows = answer_stop_next_bus(
                routes_data,
                schema.stop,
                schema.after,
                schema.before,
                schema.period_range,
            )
        else:
            answer, rows = answer_stop_upcoming(
                routes_data,
                schema.stop,
                schema.after,
                schema.before,
                schema.period_range,
            )
        cursor = make_cursor(
            intent="stop_upcoming",
            stop=schema.stop,
            after=schema.after,
            before=schema.before,
            period_range=schema.period_range,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "route_reach" and schema.route and schema.destination:
        if result_mode == "next":
            answer, rows = answer_route_reach_next(
                routes_data,
                schema.route,
                schema.destination,
                schema.after,
                schema.before,
                schema.period_range,
            )
        else:
            answer, rows = answer_route_reach(
                routes_data,
                schema.route,
                schema.destination,
                schema.after,
                schema.before,
                schema.period_range,
            )
        cursor = make_cursor(
            intent="route_reach",
            route=schema.route,
            destination=schema.destination,
            after=schema.after,
            before=schema.before,
            period_range=schema.period_range,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "route_plan" and schema.destination:
        origin_use = schema.origin or "斗六火車站"
        answer, rows = answer_route_plan(
            routes_data,
            schema.destination,
            origin_use,
            schema.after,
        )
        cursor = make_cursor(
            intent="route_plan",
            origin=origin_use,
            destination=schema.destination,
            after=schema.after,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "return_plan" and schema.origin:
        destination_use = schema.destination or "斗六火車站"
        answer, rows = answer_return_plan(
            routes_data,
            schema.origin,
            destination_use,
            schema.after,
        )
        cursor = make_cursor(
            intent="return_plan",
            origin=schema.origin,
            destination=destination_use,
            after=schema.after,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "travel_time" and schema.destination:
        origin_use = schema.origin or "斗六火車站"
        answer, rows = answer_travel_time(
            routes_data,
            schema.destination,
            origin_use,
            schema.after,
        )
        cursor = make_cursor(
            intent="travel_time",
            origin=origin_use,
            destination=schema.destination,
            after=schema.after,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    if schema.intent == "arrival_feasible" and schema.destination and schema.arrive_by:
        origin_use = schema.origin or "斗六火車站"
        answer, rows = answer_arrival_feasible(
            routes_data,
            schema.destination,
            origin_use,
            schema.after,
            schema.arrive_by,
        )
        cursor = make_cursor(
            intent="arrival_feasible",
            origin=origin_use,
            destination=schema.destination,
            after=schema.after,
            before=schema.arrive_by,
            offset=0,
            page_size=1,
        )
        return build_paginated_response(answer=answer, rows=rows, cursor=cursor, original_question=raw_question)

    fallback = rag_answer(raw_question) if raw_question else "目前無法判斷這個問題。"
    return {
        "answer": fallback,
        "items": [],
        "cursor": None,
        "has_more": False,
        "total_count": 0,
    }


# ---------------------------------
# 根據 cursor 往後抓
# ---------------------------------
def run_cursor_query(cursor: dict[str, Any]):
    if not cursor:
        return {
            "answer": "沒有可延續的查詢。",
            "items": [],
            "cursor": None,
            "has_more": False,
            "total_count": 0,
        }

    intent = cursor.get("intent")
    offset = cursor.get("offset", 0)
    page_size = cursor.get("page_size", 1)

    route = cursor.get("route")
    stop = cursor.get("stop")
    origin = cursor.get("origin")
    destination = cursor.get("destination")
    after = cursor.get("after")
    before = cursor.get("before")
    period_range = cursor.get("period_range")

    if intent == "route_schedule" and route:
        answer, rows = answer_route_schedule(routes_data, route, after, before, period_range)

    elif intent == "stop_upcoming" and stop:
        answer, rows = answer_stop_upcoming(routes_data, stop, after, before, period_range)

    elif intent == "route_reach" and route and destination:
        answer, rows = answer_route_reach(routes_data, route, destination, after, before, period_range)

    elif intent == "route_plan" and destination:
        answer, rows = answer_route_plan(routes_data, destination, origin or "斗六火車站", after)

    elif intent == "return_plan" and origin:
        answer, rows = answer_return_plan(routes_data, origin, destination or "斗六火車站", after)

    elif intent == "travel_time" and destination:
        answer, rows = answer_travel_time(routes_data, destination, origin or "斗六火車站", after)

    elif intent == "arrival_feasible" and destination and before:
        answer, rows = answer_arrival_feasible(routes_data, destination, origin or "斗六火車站", after, before)

    else:
        return {
            "answer": "cursor 無效，無法繼續查詢。",
            "items": [],
            "cursor": None,
            "has_more": False,
            "total_count": 0,
        }

    page_items, next_offset, has_more = paginate_items(
        rows,
        offset=offset,
        page_size=page_size,
    )

    next_cursor = dict(cursor)
    next_cursor["offset"] = next_offset
    next_cursor["page_size"] = page_size

    conversation_state["last_cursor"] = next_cursor if has_more else cursor

    single_answer = build_single_item_answer(intent, page_items, fallback_answer=answer)

    return {
        "answer": convert_output_text(single_answer),
        "items": page_items,
        "cursor": next_cursor,
        "has_more": has_more,
        "total_count": len(rows),
    }


# ---------------------------------
# 基本路由
# ---------------------------------
@app.get("/")
def root():
    return {"message": "Yunlin Bus API is running"}


@app.post("/reload")
def reload_data():
    global routes_data, aliases_raw
    routes_data = load_routes()
    aliases_raw = load_aliases_raw()
    return {"message": "routes and aliases reloaded successfully"}


@app.post("/parse")
def parse_only(req: ParseRequest):
    schema = parse_with_optional_llm(
        question=req.question,
        routes=routes_data,
        raw_aliases=aliases_raw,
        llm_extractor=llm_extract_schema,
    )
    return schema.to_dict()


# ---------------------------------
# 原本各功能 API
# ---------------------------------
@app.post("/route-schedule")
def route_schedule(req: RouteScheduleRequest):
    answer, rows = answer_route_schedule(routes_data, req.route, req.after, req.before)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/stop-upcoming")
def stop_upcoming(req: StopUpcomingRequest):
    answer, rows = answer_stop_upcoming(routes_data, req.stop, req.after, req.before)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/route-reach")
def route_reach(req: RouteReachRequest):
    answer, rows = answer_route_reach(routes_data, req.route, req.destination, req.after, req.before)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/route-plan")
def route_plan(req: RoutePlanRequest):
    answer, rows = answer_route_plan(routes_data, req.destination, req.origin, req.after)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/return-plan")
def return_plan(req: ReturnPlanRequest):
    answer, rows = answer_return_plan(routes_data, req.from_place, req.destination, req.after)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/travel-time")
def travel_time(req: TravelTimeRequest):
    answer, rows = answer_travel_time(routes_data, req.destination, req.origin, req.after)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/arrival-feasible")
def arrival_feasible(req: ArrivalFeasibleRequest):
    answer, rows = answer_arrival_feasible(
        routes_data,
        req.destination,
        req.origin,
        req.after,
        req.arrive_by,
    )
    return {"answer": convert_output_text(answer), "rows": rows}


# ---------------------------------
# ask：第一次查詢
# ---------------------------------
@app.post("/ask")
def ask(req: AskRequest):
    schema = parse_with_optional_llm(
        question=req.question,
        routes=routes_data,
        raw_aliases=aliases_raw,
        llm_extractor=llm_extract_schema,
    )

    result = run_schema_query(schema)
    result["schema"] = schema.to_dict()
    return result


# ---------------------------------
# ask-more：往後抓
# ---------------------------------
@app.post("/ask-more")
def ask_more(req: AskMoreRequest):
    cursor = req.cursor or conversation_state.get("last_cursor")
    result = run_cursor_query(cursor)
    return result