from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bus_core import (
    load_routes,
    answer_route_schedule,
    answer_stop_upcoming,
    answer_route_reach,
    answer_route_plan,
    answer_return_plan,
    answer_travel_time,
    answer_arrival_feasible,
    convert_output_text,
)
from nlu import (
    parse_with_optional_llm,
    llm_extract_schema,
)
from formatter import ResponseFormatter
from router import QueryRouter
from state_manager import ConversationStateManager
from state_store import MemoryStateStore, RedisStateStore
from validator import (
    ValidationError,
    validate_cursor,
    validate_question,
    validate_session_id,
)
from logger import log_request


from tdx_client import (
    get_yunlin_routes,
    get_yunlin_stop_of_route,
    get_yunlin_eta,
    get_yunlin_realtime_by_frequency,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ALIASES_JSON = DATA_DIR / "aliases.json"

REDIS_ENABLED = os.getenv("REDIS_ENABLED", "0") == "1"
ALLOW_DEFAULT_SESSION_ID = os.getenv("ALLOW_DEFAULT_SESSION_ID", "1") == "1"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases_raw() -> dict:
    return load_json(ALIASES_JSON)


def build_state_manager() -> ConversationStateManager:
    if REDIS_ENABLED:
        store = RedisStateStore()
    else:
        store = MemoryStateStore()
    return ConversationStateManager(store=store, expire_minutes=10)


def resolve_session_id(session_id: Optional[str]) -> str:
    if session_id:
        return validate_session_id(session_id)

    if ALLOW_DEFAULT_SESSION_ID:
        return "default"

    raise ValidationError("session_id 為必填。")


app = FastAPI(title="Yunlin Bus Assistant API")

routes_data = load_routes()
aliases_raw = load_aliases_raw()

state_manager = build_state_manager()
formatter = ResponseFormatter()
router = QueryRouter(
    routes_data=routes_data,
    formatter=formatter,
    state_manager=state_manager,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class ParseRequest(BaseModel):
    question: str


class AskMoreRequest(BaseModel):
    session_id: Optional[str] = None
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
    arrive_by: Optional[str] = None


@app.get("/")
def root():
    return {
        "message": "Yunlin Bus API is running",
        "redis_enabled": REDIS_ENABLED,
        "allow_default_session_id": ALLOW_DEFAULT_SESSION_ID,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": "2026-04-18"}


@app.post("/reload")
def reload_data():
    global routes_data, aliases_raw, router, state_manager

    routes_data = load_routes()
    aliases_raw = load_aliases_raw()
    state_manager = build_state_manager()

    router = QueryRouter(
        routes_data=routes_data,
        formatter=formatter,
        state_manager=state_manager,
    )

    return {"message": "routes and aliases reloaded successfully"}


@app.post("/parse")
def parse_only(req: ParseRequest):
    try:
        validate_question(req.question)
    except ValidationError as e:
        return {"error": str(e)}

    schema = parse_with_optional_llm(
        question=req.question,
        routes=routes_data,
        raw_aliases=aliases_raw,
        llm_extractor=llm_extract_schema,
    )
    return schema.to_dict()


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
    answer, rows = answer_route_reach(
        routes_data, req.route, req.destination, req.after, req.before
    )
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/route-plan")
def route_plan(req: RoutePlanRequest):
    answer, rows = answer_route_plan(routes_data, req.destination, req.origin, req.after)
    return {"answer": convert_output_text(answer), "rows": rows}


@app.post("/return-plan")
def return_plan(req: ReturnPlanRequest):
    answer, rows = answer_return_plan(
        routes_data, req.from_place, req.destination, req.after
    )
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


@app.post("/ask")
def ask(req: AskRequest):
    try:
        validate_question(req.question)
        session_id = resolve_session_id(req.session_id)
    except ValidationError as e:
        return {
            "answer": str(e),
            "items": [],
            "cursor": None,
            "has_more": False,
            "total_count": 0,
        }

    log_request(
        "ask",
        {
            "session_id": session_id,
            "question": req.question,
        },
    )

    schema = parse_with_optional_llm(
        question=req.question,
        routes=routes_data,
        raw_aliases=aliases_raw,
        llm_extractor=llm_extract_schema,
    )

    result = router.handle_schema(schema, session_id)
    result["schema"] = schema.to_dict()
    result["session_id"] = session_id
    return result


@app.post("/ask-more")
def ask_more(req: AskMoreRequest):
    try:
        session_id = resolve_session_id(req.session_id)
        validate_cursor(req.cursor)
    except ValidationError as e:
        return {
            "answer": str(e),
            "items": [],
            "cursor": None,
            "has_more": False,
            "total_count": 0,
        }

    log_request(
        "ask_more",
        {
            "session_id": session_id,
            "cursor": req.cursor,
        },
    )

    result = router.handle_cursor(req.cursor, session_id)
    result["session_id"] = session_id
    return result


@app.get("/tdx/routes")
def tdx_routes():
    data = get_yunlin_routes()
    return {
        "count": len(data),
        "routes": data,
    }


@app.get("/tdx/stop-of-route/{route_name}")
def tdx_stop_of_route(route_name: str):
    data = get_yunlin_stop_of_route(route_name)
    return {
        "route": route_name,
        "data": data,
    }


@app.get("/tdx/eta/{route_name}")
def tdx_eta(route_name: str):
    data = get_yunlin_eta(route_name)

    simple_data = []

    for item in data:
        stop_name = item.get("StopName", {}).get("Zh_tw")
        route_name_zh = item.get("RouteName", {}).get("Zh_tw")
        direction = item.get("Direction")
        estimate_time = item.get("EstimateTime")
        stop_status = item.get("StopStatus")

        if estimate_time is not None:
            estimate_text = f"{estimate_time // 60} 分鐘"
        else:
            estimate_text = get_stop_status_text(stop_status)

        simple_data.append({
            "route": route_name_zh,
            "stop": stop_name,
            "direction": direction,
            "estimate_time": estimate_time,
            "estimate_text": estimate_text,
            "stop_status": stop_status,
        })

    return {
        "route": route_name,
        "count": len(simple_data),
        "items": simple_data,
    }


@app.get("/tdx/realtime")
def tdx_realtime():
    data = get_yunlin_realtime_by_frequency()
    return {
        "count": len(data),
        "items": data,
    }


@app.get("/tdx/realtime/{route_name}")
def tdx_realtime_by_route(route_name: str):
    data = get_yunlin_realtime_by_frequency(route_name)
    return {
        "route": route_name,
        "count": len(data),
        "items": data,
    }


def get_stop_status_text(status: int | None) -> str:
    status_map = {
        0: "正常",
        1: "尚未發車",
        2: "交管不停靠",
        3: "末班車已過",
        4: "今日未營運",
    }

    return status_map.get(status, "無預估資料")