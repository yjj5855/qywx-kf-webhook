from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request

from src.api_bindings import router as bindings_router
from src.api_memory import router as memory_router
from src.client import get_client
from src.config import settings
from src.handler import get_handler
from src.models import CallbackRequest, CallbackResponse

# ---- 日志配置 ----

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
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

# 只给项目模块挂 handler，避免 uvicorn 的 handler 也写 app.log 造成重复。
# 注意：以 `python -m src.main` 运行时模块全名带 "src." 前缀，两种名字都要覆盖，
# 否则 handler/dify_client 等模块的日志只会打到 stderr，app.log 里看不到。
_project_loggers = (
    "__main__",
    "main", "handler", "client", "dify_client", "exporter", "kb",
    "binding", "session_store", "memory", "company", "api_bindings", "api_memory",
    "src.main", "src.handler", "src.client", "src.dify_client",
    "src.exporter", "src.kb", "src.binding", "src.session_store",
    "src.memory", "src.company", "src.api_bindings", "src.api_memory",
)
for _name in _project_loggers:
    _pkg = logging.getLogger(_name)
    _pkg.setLevel(logging.INFO)
    _pkg.addHandler(_log_handler)
    _pkg.propagate = False  # 不往根 logger 传播，避免重复

# 静默第三方库日志
for _noisy in ("httpx", "httpx._client", "uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 消息去重：WorkTool 可能短时间内重复推送同一消息
_seen_message_ids: set[str] = set()
_MAX_SEEN_IDS = 2000


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动知识库增量导出定时任务，退出时清理"""
    from src.client import client as _client
    from src.exporter import kb_export_loop

    export_task = asyncio.create_task(kb_export_loop(settings.dify_export_interval))
    yield
    export_task.cancel()
    if _client:
        await _client.close()


app = FastAPI(title="WorkTool Callback Service", lifespan=lifespan)
app.include_router(bindings_router, prefix="/api")
app.include_router(memory_router, prefix="/api")


async def _process_message(req: CallbackRequest, robot_id: str) -> None:
    """异步处理消息，通过 send_text 回复"""
    # 消息去重：优先用 message_id，为空则用图片 base64 的 hash
    dedup_key = req.message_id or ""
    if not dedup_key and req.file_base64:
        dedup_key = hashlib.md5(req.file_base64.encode()).hexdigest()
    if dedup_key:
        if dedup_key in _seen_message_ids:
            logger.debug("重复消息 dedup_key=%r，跳过", dedup_key[:16])
            return
        _seen_message_ids.add(dedup_key)
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
        result = await handler.handle(req, robot_id)
        if result.reply_text:
            client = get_client(robot_id)
            send_result = await client.send_text(to=req.chat_id, content=result.reply_text)
            logger.info(
                "webhook 已回复 chat_id=%r reason=%r reply=%r worktool=%s",
                req.chat_id, result.reason, result.reply_text, send_result,
            )
        elif result.sent_internally:
            logger.info(
                "主工作流内部已直接回复 chat_id=%r（webhook 不重复发送）",
                req.chat_id,
            )
        else:
            logger.info(
                "本次不回复 chat_id=%r（%s）",
                req.chat_id, result.reason or "未产生回复",
            )
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
