from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bus_core import (
    answer_arrival_feasible,
    answer_return_plan,
    answer_route_plan,
    answer_route_reach,
    answer_route_schedule,
    answer_stop_upcoming,
    answer_travel_time,
    convert_output_text,
    load_routes,
)
from formatter import ResponseFormatter
from logger import log_request
from nlu import llm_extract_schema, parse_with_optional_llm
from realtime_core import (
    answer_realtime_eta_from_question,
    answer_realtime_position_from_question,
    extract_route_from_question,
    is_position_question,
    is_realtime_question,
    legacy_response,
)
from router import QueryRouter
from state_manager import ConversationStateManager
from state_store import MemoryStateStore, RedisStateStore
from tdx_client import get_yunlin_realtime, get_yunlin_routes, get_yunlin_stop_of_route
from validator import ValidationError, validate_cursor, validate_question, validate_session_id


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


def get_last_realtime_context(session_id: str) -> dict[str, Any]:
    state = state_manager.get_state(session_id)
    context = state.get("last_realtime")

    if isinstance(context, dict):
        return context

    return {}


def save_last_realtime_context(
    session_id: str,
    context: Optional[dict[str, Any]],
) -> None:
    if not context:
        return

    state = state_manager.get_state(session_id)

    previous_context = state.get("last_realtime")
    if isinstance(previous_context, dict):
        merged_context = dict(previous_context)
    else:
        merged_context = {}

    for key, value in context.items():
        if value is not None:
            merged_context[key] = value

    state["last_realtime"] = merged_context
    state_manager.save(session_id, state)


def strip_internal_fields(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(result)
    cleaned.pop("_context", None)
    return cleaned


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
    return {"version": "2026-05-14-realtime-traditional-context-next-bus"}


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
    answer, rows = answer_route_schedule(
        routes_data,
        req.route,
        req.after,
        req.before,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/stop-upcoming")
def stop_upcoming(req: StopUpcomingRequest):
    answer, rows = answer_stop_upcoming(
        routes_data,
        req.stop,
        req.after,
        req.before,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/route-reach")
def route_reach(req: RouteReachRequest):
    answer, rows = answer_route_reach(
        routes_data,
        req.route,
        req.destination,
        req.after,
        req.before,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/route-plan")
def route_plan(req: RoutePlanRequest):
    answer, rows = answer_route_plan(
        routes_data,
        req.destination,
        req.origin,
        req.after,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/return-plan")
def return_plan(req: ReturnPlanRequest):
    answer, rows = answer_return_plan(
        routes_data,
        req.from_place,
        req.destination,
        req.after,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/travel-time")
def travel_time(req: TravelTimeRequest):
    answer, rows = answer_travel_time(
        routes_data,
        req.destination,
        req.origin,
        req.after,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/arrival-feasible")
def arrival_feasible(req: ArrivalFeasibleRequest):
    answer, rows = answer_arrival_feasible(
        routes_data,
        req.destination,
        req.origin,
        req.after,
        req.arrive_by,
    )
    return {
        "answer": convert_output_text(answer),
        "rows": rows,
    }


@app.post("/ask")
def ask(req: AskRequest):
    try:
        validate_question(req.question)
        session_id = resolve_session_id(req.session_id)
    except ValidationError as e:
        return legacy_response(
            answer=str(e),
            items=[],
            cursor=None,
            has_more=False,
            total_count=0,
        )

    log_request(
        "ask",
        {
            "session_id": session_id,
            "question": req.question,
        },
    )

    if is_realtime_question(req.question):
        explicit_route = extract_route_from_question(req.question)
        last_realtime = get_last_realtime_context(session_id)

        context_route = last_realtime.get("route")
        context_stop = last_realtime.get("stop")
        context_last_answer_time = last_realtime.get("last_answer_time")

        try:
            if is_position_question(req.question):
                result = answer_realtime_position_from_question(
                    question=req.question,
                    route=explicit_route,
                    context_route=context_route,
                )
            else:
                result = answer_realtime_eta_from_question(
                    question=req.question,
                    routes_data=routes_data,
                    route=explicit_route,
                    context_route=context_route,
                    context_stop=context_stop,
                    context_last_answer_time=context_last_answer_time,
                )

            save_last_realtime_context(
                session_id=session_id,
                context=result.get("_context"),
            )

            return strip_internal_fields(result)

        except Exception:
            return legacy_response(
                answer="目前即時公車資料暫時無法取得，請稍後再試。",
                items=[],
                cursor=None,
                has_more=False,
                total_count=0,
            )

    schema = parse_with_optional_llm(
        question=req.question,
        routes=routes_data,
        raw_aliases=aliases_raw,
        llm_extractor=llm_extract_schema,
    )
    result = router.handle_schema(schema, session_id)

    return legacy_response(
        answer=result.get("answer", ""),
        items=result.get("items", []),
        cursor=result.get("cursor"),
        has_more=result.get("has_more", False),
        total_count=result.get("total_count", len(result.get("items", []))),
    )


@app.post("/ask-more")
def ask_more(req: AskMoreRequest):
    try:
        session_id = resolve_session_id(req.session_id)
        validate_cursor(req.cursor)
    except ValidationError as e:
        return legacy_response(
            answer=str(e),
            items=[],
            cursor=None,
            has_more=False,
            total_count=0,
        )

    log_request(
        "ask_more",
        {
            "session_id": session_id,
            "cursor": req.cursor,
        },
    )

    result = router.handle_cursor(req.cursor, session_id)

    return legacy_response(
        answer=result.get("answer", ""),
        items=result.get("items", []),
        cursor=result.get("cursor"),
        has_more=result.get("has_more", False),
        total_count=result.get("total_count", len(result.get("items", []))),
    )


@app.get("/tdx/routes")
def tdx_routes():
    data = get_yunlin_routes()
    return {
        "count": len(data),
        "items": data,
    }


@app.get("/tdx/stop-of-route/{route_name}")
def tdx_stop_of_route(route_name: str):
    data = get_yunlin_stop_of_route(route_name)
    return {
        "route": route_name,
        "count": len(data),
        "items": data,
    }


@app.get("/tdx/eta/{route_name}")
def tdx_eta(route_name: str):
    return answer_realtime_eta_from_question(
        question=f"{route_name} 現在多久到？",
        routes_data=routes_data,
        route=route_name,
    )


@app.get("/tdx/eta/{route_name}/stop/{stop_name}")
def tdx_eta_by_stop(route_name: str, stop_name: str):
    return answer_realtime_eta_from_question(
        question=f"{route_name} {stop_name} 現在多久到？",
        routes_data=routes_data,
        route=route_name,
        stop=stop_name,
    )


@app.get("/tdx/realtime")
def tdx_realtime_all():
    data = get_yunlin_realtime()
    return {
        "count": len(data),
        "items": data,
    }


@app.get("/tdx/realtime/{route_name}")
def tdx_realtime_route(route_name: str):
    return answer_realtime_position_from_question(
        question=f"{route_name} 現在在哪？",
        route=route_name,
    )