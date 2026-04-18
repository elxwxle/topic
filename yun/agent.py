from __future__ import annotations

import asyncio
import os
from typing import Any

import requests
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    room_io,
    inference,
)
from livekit.plugins import ai_coustics, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel


load_dotenv(".env.local")
load_dotenv(".env.livekit", override=False)

BUS_API_BASE = os.getenv("BUS_API_BASE", "http://127.0.0.1:8000")
BUS_API_TIMEOUT = float(os.getenv("BUS_API_TIMEOUT", "20"))
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "yunlin-bus-agent")


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BUS_API_BASE.rstrip('/')}{path}"
    resp = requests.post(url, json=payload, timeout=BUS_API_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("API response is not a JSON object")
    return data


class YunlinBusVoiceAgent(Agent):
    def __init__(self, bus_session_id: str) -> None:
        self.bus_session_id = bus_session_id
        super().__init__(
            instructions="""
你是雲林公車語音助理。

規則：
1. 只要是公車、站牌、路線、發車時間、下一班、幾點到、怎麼去、怎麼回來、轉乘、多久到，全部優先使用工具，不可自行猜測。
2. 回答一律使用繁體中文。
3. 回答要自然、口語、簡短，適合直接唸出來。
4. 工具回傳的 answer 是最高優先，盡量忠實轉述，不要亂改意思。
5. 如果使用者是在延續上一題，例如：
   - 還有嗎
   - 更晚的
   - 下一班
   - 再一個
   - 還有其他選擇嗎
   優先呼叫 ask_bus_more。
6. 如果工具查不到，就直接誠實說查不到，不要自己編答案。
"""
        )

    @function_tool()
    async def ask_bus(self, context: RunContext, question: str) -> str:
        """
        查詢雲林公車問題。
        當使用者第一次問問題，或問題內容已經包含完整條件時使用。
        例如：斗六火車站到虎尾怎麼去、下一班到北港的車、201有沒有到高鐵雲林站。
        """
        try:
            result = await asyncio.to_thread(
                _post_json,
                "/ask",
                {
                    "question": question,
                    "session_id": self.bus_session_id,
                },
            )
        except Exception as e:
            return f"目前公車查詢服務暫時無法連線，錯誤是：{e}"

        answer = str(result.get("answer") or "目前沒有查到結果。").strip()
        has_more = bool(result.get("has_more", False))

        if has_more:
            answer += " 如果你要，我也可以繼續幫你看下一班或更晚的車。"

        return answer

    @function_tool()
    async def ask_bus_more(self, context: RunContext) -> str:
        """
        延續上一個查詢，查看下一筆、下一班、更晚的班次或其他候選結果。
        當使用者說「還有嗎」、「更晚的」、「下一班」、「再一個」時使用。
        """
        try:
            result = await asyncio.to_thread(
                _post_json,
                "/ask-more",
                {
                    "session_id": self.bus_session_id,
                },
            )
        except Exception as e:
            return f"目前延續查詢失敗，錯誤是：{e}"

        answer = str(result.get("answer") or "沒有更多結果了。").strip()
        has_more = bool(result.get("has_more", False))

        if not has_more:
            answer += " 目前這一輪結果已經到最後了。"

        return answer


server = AgentServer()


@server.rtc_session(agent_name=LIVEKIT_AGENT_NAME)
async def entrypoint(ctx: agents.JobContext):
    room_name = getattr(ctx.room, "name", "default-room") or "default-room"
    bus_session_id = f"livekit:{room_name}"

    session = AgentSession(
        stt=inference.STT(
            model="cartesia/ink-whisper",
            language="zh",
        ),
        llm="openai/gpt-5.3-chat-latest",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),
        ),
    )

    await session.start(
        room=ctx.room,
        agent=YunlinBusVoiceAgent(bus_session_id=bus_session_id),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_L
                ),
            ),
        ),
    )

    await session.generate_reply(
        instructions=(
            "請用繁體中文簡短打招呼，並告訴使用者你可以幫忙查雲林公車、"
            "下一班、怎麼去、怎麼回來、多久到，也可以繼續往下查更晚的班次。"
        )
    )


if __name__ == "__main__":
    agents.cli.run_app(server)