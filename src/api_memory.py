"""对话记忆接口：把机器人最终回复文本记录到本项目，供下轮意图分类注入上下文。

与"工作流内 HTTP 节点回调本项目"相比，适配层从工作流返回中直接拿到 final_text，
在这里记录更简单且不会因记录失败影响工作流主流程。
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth import require_admin
from src.binding import BindingStore
from src.config import settings
from src.exporter import export_once
from src.kb import export_turns
from src.memory import ChatMemoryStore, format_time_cn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["memory"], dependencies=[Depends(require_admin)])

_store: ChatMemoryStore | None = None


class RecordMessageRequest(BaseModel):
    session_id: str
    sender_name: str = ""      # 说话人名称（receivedName）
    content: str = ""          # 新格式：单条消息内容（role 区分 user/bot）
    role: str = "user"         # user / bot
    group_name: str = ""       # 真实群名（群聊导出按群匹配用）
    # 兼容旧格式：问答对（提供时按两条消息写入，user + bot）
    user_message: str = ""
    reply_text: str = ""


class ExportMemoryRequest(BaseModel):
    session_id: str
    since_id: int = 0      # 只导出 id 大于该值的对话（增量归档用）
    limit: int = 50
    seq: int = 0           # 文档名序号（可选，避免同名覆盖）


def _get_store() -> ChatMemoryStore:
    global _store
    if _store is None:
        _store = ChatMemoryStore(settings.dify_db_path)
    return _store


@router.post("/record")
async def record_message(req: RecordMessageRequest):
    store = _get_store()
    if req.content:
        # 新格式：单条消息
        store.append(req.session_id, req.content, sender_name=req.sender_name, role=req.role, group_name=req.group_name)
    else:
        # 兼容旧格式：问答对拆两条消息（user + bot）
        if req.user_message:
            store.append(req.session_id, req.user_message, sender_name=req.sender_name, role="user", group_name=req.group_name)
        if req.reply_text:
            store.append(req.session_id, req.reply_text, sender_name="机器人", role="bot", group_name=req.group_name)
    return {"code": 0, "message": "ok"}


@router.get("/history")
async def history(session_id: str = "", limit: int = 6):
    if not session_id:
        return {"code": 0, "message": "ok", "data": []}
    turns = _get_store().history(session_id, limit)
    for t in turns:
        t["time"] = format_time_cn(t.get("created_at") or "")
    return {"code": 0, "message": "ok", "data": turns}


@router.post("/export")
async def export_memory(req: ExportMemoryRequest):
    """把某群最近的对话导出成知识库文档（写入群绑定的 Dify 数据集）。

    session_id 形如 "1:测试二群"（roomType:chatId），仅支持群聊会话（roomType 1/3）。
    返回 data.last_id 供下次作为 since_id 增量导出。
    """
    if not settings.dify_dataset_key:
        return {"code": -1, "message": "未配置 WT_DIFY_DATASET_KEY（需 Dify 数据集权限 Key）"}

    room_type, _, chat_id = req.session_id.partition(":")
    if room_type not in ("1", "3") or not chat_id:
        return {"code": -1, "message": "仅支持群聊会话导出，session_id 格式为 roomType:chatId"}

    # 回调只有群名，按群名反查绑定（group_id 为 G 编码）
    binding = BindingStore(settings.dify_db_path).get_by_group_name("wecom", chat_id)
    dataset_id = (binding or {}).get("memory_dataset_id") or ""
    if not binding or not dataset_id:
        return {"code": -1, "message": "群未绑定知识库（请先通过 POST /api/bindings 设置 memory_dataset_id）"}

    turns = _get_store().history_since(req.session_id, after_id=req.since_id, limit=req.limit)
    if not turns:
        return {"code": 0, "message": "无新对话可导出", "data": {"exported": 0, "last_id": req.since_id}}

    try:
        doc = await export_turns(
            base_url=settings.dify_base_url,
            api_key=settings.dify_dataset_key,
            dataset_id=dataset_id,
            name_prefix=f"群对话_{chat_id}",
            turns=turns,
            seq=req.seq,
        )
    except httpx.HTTPError as exc:
        logger.exception("知识库写入失败 session=%r", req.session_id)
        return {"code": -1, "message": f"写入知识库失败：{exc}"}
    except ValueError as exc:
        return {"code": -1, "message": str(exc)}

    last_id = turns[-1]["id"]
    return {
        "code": 0,
        "message": "ok",
        "data": {"exported": len(turns), "last_id": last_id, "document": doc},
    }


@router.post("/sync")
async def sync_all():
    """手动全量同步：把所有绑定知识库的群增量导出一次（与每日定时同步相同逻辑）。

    返回 {group_id: 导出条数}，-1 表示该群导出失败（见日志）。
    """
    if not settings.dify_dataset_key:
        return {"code": -1, "message": "未配置 WT_DIFY_DATASET_KEY（需 Dify 数据集权限 Key）"}
    try:
        results = await export_once()
    except Exception:
        logger.exception("手动知识库同步失败")
        return {"code": -1, "message": "同步失败，详见日志"}
    return {"code": 0, "message": "ok", "data": results}


class SetStageRequest(BaseModel):
    session_id: str           # 会话标识，格式 roomType:chat_id，如 "1:测试二群"（外部后台按群名拼接）
    stage: int                # 服务阶段 0~4（0未开始 1初次触达 2转化签约 3签约后交付 4长期服务）


@router.post("/stage")
async def set_session_stage(req: SetStageRequest):
    """外部后台设置/重置会话服务阶段（如客服在其他后台完成初次触达后置 stage=1）。

    用途：0→1 等阶段可能不在机器人回调链路内完成（介绍话术由人工在其他后台发送），
    后台发完介绍后调用本接口把会话 stage 置为对应值，机器人后续按该阶段响应，
    避免重复发送第一阶段介绍。
    """
    if not req.session_id:
        return {"code": -1, "message": "缺少 session_id"}
    store = _get_store()
    store.set_stage(req.session_id, req.stage)
    return {
        "code": 0,
        "message": "ok",
        "data": {"session_id": req.session_id, "stage": store.get_stage(req.session_id)},
    }


@router.get("/stage")
async def get_session_stage(session_id: str = ""):
    """查询会话当前服务阶段。"""
    if not session_id:
        return {"code": -1, "message": "缺少 session_id"}
    return {
        "code": 0,
        "message": "ok",
        "data": {"session_id": session_id, "stage": _get_store().get_stage(session_id)},
    }
