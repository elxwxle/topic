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
from validator import (
    ValidationError,
    validate_cursor,
    validate_question,
    validate_session_id,
)
from logger import log_request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ALIASES_JSON = DATA_DIR / "aliases.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases_raw() -> dict:
    return load_json(ALIASES_JSON)


app = FastAPI(title="Yunlin Bus Assistant API")

routes_data = load_routes()
aliases_raw = load_aliases_raw()

state_manager = ConversationStateManager(expire_minutes=10)
formatter = ResponseFormatter()
router = QueryRouter(
    routes_data=routes_data,
    formatter=formatter,
    state_manager=state_manager,
)


class AskRequest(BaseModel):
    question: str
    session_id: str = "default"


class ParseRequest(BaseModel):
    question: str


class AskMoreRequest(BaseModel):
    session_id: str = "default"
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
    return {"message": "Yunlin Bus API is running"}


@app.post("/reload")
def reload_data():
    global routes_data, aliases_raw, router

    routes_data = load_routes()
    aliases_raw = load_aliases_raw()

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


@app.post("/ask")
def ask(req: AskRequest):
    try:
        validate_question(req.question)
        session_id = validate_session_id(req.session_id)
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
    return result


@app.post("/ask-more")
def ask_more(req: AskMoreRequest):
    try:
        session_id = validate_session_id(req.session_id)
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

    return router.handle_cursor(req.cursor, session_id)