from __future__ import annotations

from typing import Any, Optional

from bus_core import (
    answer_arrival_feasible,
    answer_route_plan,
    answer_route_reach,
    answer_route_schedule,
    answer_return_plan,
    answer_stop_upcoming,
    answer_travel_time,
)
from entity_resolver import resolve_schema_places
from pagination import make_cursor, paginate_items
from formatter import ResponseFormatter
from state_manager import ConversationStateManager
from validator import ValidationError, validate_cursor, validate_schema_basic
from logger import log_router_decision, log_result

try:
    from rag_core import rag_answer
except Exception:
    def rag_answer(query: str) -> str:
        return "目前找不到可補充的說明資料。"


DEFAULT_ORIGIN = "斗六火車站"
DEFAULT_DESTINATION = "斗六火車站"


class QueryRouter:
    def __init__(
        self,
        *,
        routes_data: dict,
        formatter: ResponseFormatter,
        state_manager: ConversationStateManager,
    ):
        self.routes_data = routes_data
        self.formatter = formatter
        self.state_manager = state_manager

    def _empty_result(self, answer: str) -> dict[str, Any]:
        return {
            "answer": answer,
            "items": [],
            "cursor": None,
            "has_more": False,
            "total_count": 0,
        }

    def _build_result(
        self,
        *,
        answer: str,
        rows: list[dict[str, Any]],
        cursor: dict[str, Any],
        session_id: str,
        original_question: str = "",
    ) -> dict[str, Any]:
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

        self.state_manager.set_last_cursor(
            session_id,
            next_cursor if has_more else cursor,
        )

        single_answer = self.formatter.build_single_item_answer(
            cursor.get("intent", ""),
            page_items,
            fallback_answer=answer,
        )

        if not page_items and original_question:
            rag_text = rag_answer(original_question)
            if rag_text and rag_text != "目前找不到可補充的說明資料。":
                single_answer = f"{single_answer}\n\n{rag_text}"

        result = self.formatter.format_api_response(
            answer=single_answer,
            items=page_items,
            cursor=next_cursor,
            has_more=has_more,
            total_count=len(rows),
        )

        log_result(
            {
                "session_id": session_id,
                "cursor_intent": cursor.get("intent"),
                "page_size": page_size,
                "offset": offset,
                "row_count": len(rows),
                "page_count": len(page_items),
                "has_more": has_more,
            }
        )

        return result

    def _save_query_state(
        self,
        *,
        session_id: str,
        schema,
        cursor: Optional[dict[str, Any]],
    ) -> None:
        self.state_manager.save(
            session_id,
            self.state_manager.build_query_state(
                schema_dict=schema.to_dict(),
                cursor=cursor,
            ),
        )

    def handle_schema(self, schema, session_id: str) -> dict[str, Any]:
        try:
            resolve_schema_places(self.routes_data, schema)
            validate_schema_basic(schema)
        except ValidationError as e:
            return self._empty_result(str(e))

        result_mode = getattr(schema, "result_mode", "all")
        page_size = 1 if result_mode == "single" else 9999
        raw_question = getattr(schema, "debug", {}).get("raw_question", "")

        log_router_decision(
            {
                "session_id": session_id,
                "intent": getattr(schema, "intent", None),
                "schema": schema.to_dict(),
            }
        )

        if schema.intent == "route_schedule" and schema.route:
            answer, rows = answer_route_schedule(
                self.routes_data,
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
                page_size=page_size,
            )

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self._save_query_state(session_id=session_id, schema=schema, cursor=result["cursor"])
            return result

        if schema.intent == "stop_upcoming" and schema.stop:
            answer, rows = answer_stop_upcoming(
                self.routes_data,
                schema.stop,
                schema.after,
                schema.before,
            )

            cursor = make_cursor(
                intent="stop_upcoming",
                stop=schema.stop,
                after=schema.after,
                before=schema.before,
                offset=0,
                page_size=page_size,
            )

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self._save_query_state(session_id=session_id, schema=schema, cursor=result["cursor"])
            return result

        if schema.intent == "route_reach" and schema.route and schema.destination:
            answer, rows = answer_route_reach(
                self.routes_data,
                schema.route,
                schema.destination,
                schema.after,
                schema.before,
            )

            cursor = make_cursor(
                intent="route_reach",
                route=schema.route,
                destination=schema.destination,
                after=schema.after,
                before=schema.before,
                offset=0,
                page_size=page_size,
            )

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self._save_query_state(session_id=session_id, schema=schema, cursor=result["cursor"])
            return result

        if schema.intent == "route_plan" and schema.destination:
            origin_use = schema.origin or DEFAULT_ORIGIN

            answer, rows = answer_route_plan(
                self.routes_data,
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

            schema_dict = schema.to_dict()
            schema_dict["origin"] = origin_use

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self.state_manager.save(
                session_id,
                self.state_manager.build_query_state(
                    schema_dict=schema_dict,
                    cursor=result["cursor"],
                ),
            )
            return result

        if schema.intent == "return_plan" and schema.origin:
            destination_use = schema.destination or DEFAULT_DESTINATION

            answer, rows = answer_return_plan(
                self.routes_data,
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

            schema_dict = schema.to_dict()
            schema_dict["destination"] = destination_use

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self.state_manager.save(
                session_id,
                self.state_manager.build_query_state(
                    schema_dict=schema_dict,
                    cursor=result["cursor"],
                ),
            )
            return result

        if schema.intent == "travel_time" and schema.destination:
            origin_use = schema.origin or DEFAULT_ORIGIN

            answer, rows = answer_travel_time(
                self.routes_data,
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

            schema_dict = schema.to_dict()
            schema_dict["origin"] = origin_use

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self.state_manager.save(
                session_id,
                self.state_manager.build_query_state(
                    schema_dict=schema_dict,
                    cursor=result["cursor"],
                ),
            )
            return result

        if schema.intent == "arrival_feasible" and schema.destination and schema.arrive_by:
            origin_use = schema.origin or DEFAULT_ORIGIN

            answer, rows = answer_arrival_feasible(
                self.routes_data,
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

            schema_dict = schema.to_dict()
            schema_dict["origin"] = origin_use

            result = self._build_result(
                answer=answer,
                rows=rows,
                cursor=cursor,
                session_id=session_id,
                original_question=raw_question,
            )
            self.state_manager.save(
                session_id,
                self.state_manager.build_query_state(
                    schema_dict=schema_dict,
                    cursor=result["cursor"],
                ),
            )
            return result

        fallback = self._empty_result("目前無法判斷查詢意圖。")

        if raw_question:
            rag_text = rag_answer(raw_question)
            if rag_text and rag_text != "目前找不到可補充的說明資料。":
                fallback["answer"] = f"{fallback['answer']}\n\n{rag_text}"

        return fallback

    def handle_cursor(
        self,
        cursor: Optional[dict[str, Any]],
        session_id: str,
    ) -> dict[str, Any]:
        try:
            validate_cursor(cursor)
        except ValidationError as e:
            return self._empty_result(str(e))

        if not cursor:
            cursor = self.state_manager.get_last_cursor(session_id)

        if not cursor:
            return self._empty_result("沒有可延續的查詢。")

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

        log_router_decision(
            {
                "session_id": session_id,
                "cursor_mode": True,
                "intent": intent,
                "cursor": cursor,
            }
        )

        if intent == "route_schedule":
            answer, rows = answer_route_schedule(
                self.routes_data,
                route,
                after,
                before,
                period_range,
            )
        elif intent == "stop_upcoming":
            answer, rows = answer_stop_upcoming(
                self.routes_data,
                stop,
                after,
                before,
            )
        elif intent == "route_reach":
            answer, rows = answer_route_reach(
                self.routes_data,
                route,
                destination,
                after,
                before,
            )
        elif intent == "route_plan":
            answer, rows = answer_route_plan(
                self.routes_data,
                destination,
                origin or DEFAULT_ORIGIN,
                after,
            )
        elif intent == "return_plan":
            answer, rows = answer_return_plan(
                self.routes_data,
                origin,
                destination or DEFAULT_DESTINATION,
                after,
            )
        elif intent == "travel_time":
            answer, rows = answer_travel_time(
                self.routes_data,
                destination,
                origin or DEFAULT_ORIGIN,
                after,
            )
        elif intent == "arrival_feasible":
            answer, rows = answer_arrival_feasible(
                self.routes_data,
                destination,
                origin or DEFAULT_ORIGIN,
                after,
                before,
            )
        else:
            return self._empty_result("cursor 無效，無法繼續查詢。")

        page_items, next_offset, has_more = paginate_items(
            rows,
            offset=offset,
            page_size=page_size,
        )

        next_cursor = dict(cursor)
        next_cursor["offset"] = next_offset
        next_cursor["page_size"] = page_size

        self.state_manager.set_last_cursor(
            session_id,
            next_cursor if has_more else cursor,
        )

        single_answer = self.formatter.build_single_item_answer(
            intent,
            page_items,
            fallback_answer=answer,
        )

        result = self.formatter.format_api_response(
            answer=single_answer,
            items=page_items,
            cursor=next_cursor,
            has_more=has_more,
            total_count=len(rows),
        )

        log_result(
            {
                "session_id": session_id,
                "cursor_intent": intent,
                "row_count": len(rows),
                "page_count": len(page_items),
                "has_more": has_more,
            }
        )

        return result