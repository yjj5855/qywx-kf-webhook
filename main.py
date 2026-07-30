from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from client import get_client
from config import settings
from handler import get_handler
from models import CallbackRequest, CallbackResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    yield
    from client import client as _client

    if _client:
        await _client.close()


app = FastAPI(title="WorkTool Callback Service", lifespan=lifespan)


async def _process_message(req: CallbackRequest, robot_id: str) -> None:
    """异步处理消息，通过 send_text 回复"""
    handler = get_handler(robot_id)
    reply_text = await handler.handle(req, robot_id)
    if reply_text:
        client = get_client(robot_id)
        await client.send_text(to=req.chat_id, content=reply_text)


# ---- 回调接口 ----

@app.post("/callback")
async def callback(request: Request):
    """接收 WorkTool 消息回调，立即响应后异步处理"""
    robot_id = request.query_params.get("robotId", "")

    body = await request.json()
    req = CallbackRequest.model_validate(body)

    # 异步处理消息，避免阻塞回调响应
    asyncio.create_task(_process_message(req, robot_id))

    return CallbackResponse().model_dump()


# ---- 健康检查 ----

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---- 入口 ----

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
