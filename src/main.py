from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse

from src.api_auth import router as auth_router
from src.api_bindings import router as bindings_router
from src.api_memory import router as memory_router
from src.api_workflows import router as workflows_router
from src.api_yuque import router as yuque_router
from src.client import get_client
from src.config import settings
from src.debouncer import CallbackDebouncer
from src.handler import get_handler
from src.memory import ChatMemoryStore
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
    "binding", "memory", "api_bindings", "api_memory", "api_yuque",
    "src.main", "src.handler", "src.client", "src.dify_client",
    "src.exporter", "src.kb", "src.binding", "src.memory",
    "src.api_bindings", "src.api_memory", "src.api_yuque",
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
    """应用生命周期管理：启动知识库每日定点同步任务，退出时清理"""
    from src.client import client as _client
    from src.exporter import kb_sync_loop

    export_task = asyncio.create_task(kb_sync_loop())
    yield
    export_task.cancel()
    if _client:
        await _client.close()


app = FastAPI(title="WorkTool Callback Service", lifespan=lifespan)
app.include_router(bindings_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
# 语雀外部知识库检索端点：Dify 配置的外部知识库 API 地址需以 /retrieval 结尾，
# 即填 http://<host>:8000/retrieval（新版本 Dify 会自动在填写的地址后追加 /retrieval）
app.include_router(yuque_router)


async def _handle_and_reply(req: CallbackRequest, robot_id: str) -> None:
    """执行一次处理：调用 handler 并按结果决定是否由 webhook 回复。

    由防抖调度器触发（同一会话窗口内合并，只对最新一条调用）。
    """
    try:
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


# 回调防抖：同一会话窗口内的多条消息合并为一次工作流调用（全部消息仍先入库）
_debouncer = CallbackDebouncer(window=settings.debounce_seconds, processor=_handle_and_reply)


async def _process_message(req: CallbackRequest, robot_id: str) -> None:
    """异步处理消息：去重 → 全量入库 → 防抖调度工作流调用"""
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

    logger.info(
        "收到消息 scene=%s session=%r spoken=%r at_me=%r",
        req.scene,
        req.session_id,
        req.spoken,
        req.at_me,
    )

    # 全量记录用户消息：防抖合并后部分消息不会进工作流，但必须入库，
    # 保证知识库导出与 recentContext 的完整性（机器人回复由 handler 记 bot 行）
    user_msg = req.spoken or ("[图片]" if req.text_type == 2 else "")
    if user_msg:
        try:
            ChatMemoryStore(settings.dify_db_path).append(
                req.session_id, user_msg,
                sender_name=req.received_name,
                role="user",
                group_name=req.group_name,
            )
        except Exception:
            logger.exception("记录用户消息失败 session=%r", req.session_id)

    # 防抖调度：同一会话窗口内多条消息合并，只对最新一条触发 _handle_and_reply
    _debouncer.submit(req.session_id, (req, robot_id))


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


# ---- 管理后台前端（frontend/dist，npm run build 生成）----
# 兜底路由必须注册在所有 API / 回调路由之后，否则会吞掉 /health、/callback 等。

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_MISSING_HINT = (
    "前端未构建：请在 frontend 目录执行 npm install && npm run build，"
    "或开发模式运行 npm run dev（Vite 8001 端口，/api 代理到本服务）。"
).encode("utf-8")


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    """托管前端构建产物；未知路径回退 index.html（SPA 路由）。"""
    if not FRONTEND_DIST.is_dir():
        return PlainTextResponse(_MISSING_HINT, status_code=200)
    target = (FRONTEND_DIST / (path or "")).resolve()
    if not str(target).startswith(str(FRONTEND_DIST.resolve())):
        return PlainTextResponse("forbidden", status_code=404)
    if target.is_file():
        return FileResponse(target)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return PlainTextResponse(_MISSING_HINT, status_code=200)


# ---- 入口 ----

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
