from __future__ import annotations

from typing import Any, Optional

from bus_core import convert_output_text, route_number_to_chinese, number_to_chinese


class ResponseFormatter:
    def _safe_route_name(self, item: dict[str, Any]) -> str:
        return str(item.get("route_name") or item.get("route") or "").strip()

    def _safe_route_zh(self, item: dict[str, Any]) -> str:
        route_name = self._safe_route_name(item)
        return route_number_to_chinese(route_name) if route_name else ""

    def _safe_direction(self, item: dict[str, Any]) -> str:
        return str(item.get("direction") or "未知方向").strip()

    def _safe_origin(self, item: dict[str, Any]) -> str:
        return str(
            item.get("origin")
            or item.get("from_stop")
            or item.get("start_stop")
            or item.get("board_stop")
            or "起點"
        ).strip()

    def _safe_destination(self, item: dict[str, Any]) -> str:
        return str(
            item.get("destination")
            or item.get("to_stop")
            or item.get("end_stop")
            or item.get("alight_stop")
            or "目的地"
        ).strip()

    def _safe_depart_time(self, item: dict[str, Any]) -> str:
        return str(
            item.get("depart_time")
            or item.get("start_time")
            or item.get("departure_time")
            or "未知時間"
        ).strip()

    def _safe_arrive_time(self, item: dict[str, Any]) -> str:
        return str(
            item.get("arrive_time")
            or item.get("end_time")
            or item.get("arrival_time")
            or "未知時間"
        ).strip()

    def _safe_stop_name(self, item: dict[str, Any]) -> str:
        return str(item.get("stop_name") or item.get("stop") or "該站").strip()

    def _safe_pass_time(self, item: dict[str, Any]) -> str:
        return str(
            item.get("time")
            or item.get("arrive_time")
            or item.get("start_time")
            or item.get("depart_time")
            or "未知時間"
        ).strip()

    def _safe_duration_min(self, item: dict[str, Any]) -> Optional[int]:
        val = item.get("duration_min")
        if val is None or val == "":
            return None
        try:
            return int(val)
        except Exception:
            return None

    def build_single_item_answer(
        self,
        intent: str,
        page_items: list[dict[str, Any]],
        fallback_answer: str = "",
    ) -> str:
        if not page_items:
            return fallback_answer or "目前沒有資料。"

        item = page_items[0]

        route_zh = self._safe_route_zh(item)
        direction = self._safe_direction(item)
        start_time = self._safe_depart_time(item)
        end_time = self._safe_arrive_time(item)
        stop_name = self._safe_stop_name(item)
        time_val = self._safe_pass_time(item)
        origin = self._safe_origin(item)
        destination = self._safe_destination(item)
        depart_time = self._safe_depart_time(item)
        arrive_time = self._safe_arrive_time(item)
        duration_min = self._safe_duration_min(item)

        if intent == "route_schedule":
            if route_zh:
                return (
                    f"下一班是 {route_zh}，"
                    f"方向是 {direction}，"
                    f"於 {start_time} 發車，"
                    f"於 {end_time} 抵達。"
                )
            return (
                f"下一班車，"
                f"方向是 {direction}，"
                f"於 {start_time} 發車，"
                f"於 {end_time} 抵達。"
            )

        if intent == "stop_upcoming":
            if route_zh:
                return (
                    f"在 {stop_name} 下一班是 {route_zh}，"
                    f"方向是 {direction}，"
                    f"預計 {time_val} 經過。"
                )
            return (
                f"在 {stop_name} 的下一班車，"
                f"方向是 {direction}，"
                f"預計 {time_val} 經過。"
            )

        if intent == "route_reach":
            if route_zh:
                return (
                    f"{route_zh} 可以到 {destination}，"
                    f"方向是 {direction}，"
                    f"於 {start_time} 發車，"
                    f"於 {end_time} 抵達。"
                )
            return (
                f"此班車可以到 {destination}，"
                f"方向是 {direction}，"
                f"於 {start_time} 發車，"
                f"於 {end_time} 抵達。"
            )

        if intent == "route_plan":
            if route_zh:
                answer = (
                    f"可搭乘 {route_zh}，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 從 {origin} 上車，"
                    f"預計 {arrive_time} 抵達 {destination}"
                )
            else:
                answer = (
                    f"可搭乘公車，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 從 {origin} 上車，"
                    f"預計 {arrive_time} 抵達 {destination}"
                )

            if duration_min is not None:
                answer += f"，車程約{number_to_chinese(duration_min)}分鐘。"
            else:
                answer += "。"
            return answer

        if intent == "return_plan":
            if route_zh:
                answer = (
                    f"回程可搭乘 {route_zh}，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 從 {origin} 上車，"
                    f"預計 {arrive_time} 抵達 {destination}"
                )
            else:
                answer = (
                    f"回程可搭乘公車，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 從 {origin} 上車，"
                    f"預計 {arrive_time} 抵達 {destination}"
                )

            if duration_min is not None:
                answer += f"，車程約{number_to_chinese(duration_min)}分鐘。"
            else:
                answer += "。"
            return answer

        if intent == "travel_time":
            if route_zh:
                answer = (
                    f"最快可搭乘 {route_zh}，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 出發，"
                    f"預計 {arrive_time} 抵達"
                )
            else:
                answer = (
                    f"最快可搭乘公車，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 出發，"
                    f"預計 {arrive_time} 抵達"
                )

            if duration_min is not None:
                answer += f"，車程約{number_to_chinese(duration_min)}分鐘。"
            else:
                answer += "。"
            return answer

        if intent == "arrival_feasible":
            feasible = item.get("feasible")
            if feasible is True:
                if route_zh:
                    return (
                        f"可以在指定時間前抵達。"
                        f"建議搭乘 {route_zh}，"
                        f"方向是 {direction}，"
                        f"於 {depart_time} 出發，"
                        f"預計 {arrive_time} 抵達。"
                    )
                return (
                    f"可以在指定時間前抵達。"
                    f"建議搭乘此班車，"
                    f"方向是 {direction}，"
                    f"於 {depart_time} 出發，"
                    f"預計 {arrive_time} 抵達。"
                )
            if feasible is False:
                return "目前沒有找到能在指定時間前抵達的班次。"

        return fallback_answer or "已取得資料。"

    def format_output_text(self, text: str) -> str:
        return convert_output_text(text)

    def format_api_response(
        self,
        *,
        answer: str,
        items: list[dict[str, Any]],
        cursor: Optional[dict[str, Any]],
        has_more: bool,
        total_count: int,
    ) -> dict[str, Any]:
        return {
            "answer": self.format_output_text(answer),
            "items": items,
            "cursor": cursor,
            "has_more": has_more,
            "total_count": total_count,
        }