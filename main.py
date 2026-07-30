from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request

from client import get_client
from config import settings
from handler import get_handler
from models import CallbackRequest, CallbackResponse

# ---- 日志配置 ----

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_log_handler = RotatingFileHandler(
    LOG_DIR / "app.log",
    maxBytes=2 * 1024 * 1024,  # 2MB
    backupCount=5,
    encoding="utf-8",
)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(_log_handler)


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
    try:
        logger.info(
            "收到消息 spoken=%r at_me=%r room_type=%d chat_id=%r",
            req.spoken,
            req.at_me,
            req.room_type,
            req.chat_id,
        )
        handler = get_handler(robot_id)
        reply_text = await handler.handle(req, robot_id)
        if reply_text:
            client = get_client(robot_id)
            result = await client.send_text(to=req.chat_id, content=reply_text)
            logger.info("回复成功 chat_id=%r reply=%r result=%s", req.chat_id, reply_text, result)
        else:
            logger.info("未触发回复 at_me=%r", req.at_me)
    except Exception:
        logger.exception("处理消息失败 robot_id=%s", robot_id)


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
