from __future__ import annotations

import asyncio
import json
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

# 只给项目模块挂 handler，避免 uvicorn 的 handler 也写 app.log 造成重复
_project_loggers = ("__main__", "handler", "client", "intent")
for _name in _project_loggers:
    _pkg = logging.getLogger(_name)
    _pkg.setLevel(logging.INFO)
    if not _pkg.handlers:
        _pkg.addHandler(_log_handler)
    _pkg.propagate = False  # 不往根 logger 传播，避免重复

# intent 子模块（gate 等）需要 DEBUG 级别输出 OpenAI 请求/返回详情
logging.getLogger("intent").setLevel(logging.DEBUG)

# 静默第三方库日志
for _noisy in ("httpx", "httpx._client", "uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 消息去重：WorkTool 可能短时间内重复推送同一消息
_seen_message_ids: set[str] = set()
_MAX_SEEN_IDS = 2000


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
    # 消息去重
    if req.message_id:
        if req.message_id in _seen_message_ids:
            logger.debug("重复消息 message_id=%r，跳过", req.message_id)
            return
        _seen_message_ids.add(req.message_id)
        if len(_seen_message_ids) > _MAX_SEEN_IDS:
            _seen_message_ids.clear()

    try:
        logger.info(
            "收到消息 scene=%s session=%r spoken=%r at_me=%r",
            req.scene,
            req.session_id,
            req.spoken,
            req.at_me,
        )
        handler = get_handler(robot_id)
        reply_text = await handler.handle(req, robot_id)
        if reply_text:
            client = get_client(robot_id)
            result = await client.send_text(to=req.chat_id, content=reply_text)
            logger.info("回复成功 chat_id=%r reply=%r result=%s", req.chat_id, reply_text, result)
        else:
            logger.info("无需回复 chat_id=%r", req.chat_id)
    except Exception:
        logger.exception("处理消息失败 robot_id=%s", robot_id)


# ---- 回调接口 ----

@app.post("/callback")
async def callback(request: Request):
    """接收 WorkTool 消息回调，立即响应后异步处理"""
    robot_id = request.query_params.get("robotId", "")

    body = await request.json()
    logger.info("回调请求 robotId=%r body=%s", robot_id, json.dumps(body, ensure_ascii=False))
    req = CallbackRequest.model_validate(body)

    if not robot_id:
        logger.warning("回调缺少 robotId 参数，请确认回调地址包含 ?robotId=xxx")
        return CallbackResponse(code=-1, message="缺少 robotId").model_dump()

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

    uvicorn.run(app, host=settings.host, port=settings.port)
