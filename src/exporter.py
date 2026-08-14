"""知识库增量导出定时任务（对应执行文档 §10 知识库记忆 / §12 实施步骤第 7 步）。

对每个绑定了 memory_dataset_id 的群，按 kb_last_export_id 游标增量把
chat_memory 中的真实对话写入群专属 Dify 知识库。
"""
from __future__ import annotations

import asyncio
import logging

from src.binding import BindingStore
from src.config import settings
from src.kb import export_turns
from src.memory import ChatMemoryStore

logger = logging.getLogger(__name__)

# 群聊 roomType：1=外部群 3=内部群（session_id 前缀）
_ROOM_TYPES = ("1", "3")
_BATCH = 200  # 每轮每会话最多读取的对话条数


async def export_once() -> dict:
    """对所有绑定了知识库的群做一次增量导出，返回 {group_id: 导出条数(-1=失败)}。"""
    store = BindingStore(settings.dify_db_path)
    memory = ChatMemoryStore(settings.dify_db_path)
    bindings = [b for b in store.list() if (b.get("memory_dataset_id") or "").strip()]
    results: dict[str, int] = {}

    for b in bindings:
        group_id = (b.get("group_id") or "").strip()      # G 编码稳定标识
        group_name = (b.get("group_name") or "").strip()  # 群名（session_id 与文档名用）
        dataset_id = (b.get("memory_dataset_id") or "").strip()
        if not group_id or not group_name or not dataset_id:
            continue
        cursor = int(b.get("kb_last_export_id") or 0)
        try:
            # 外部群/内部群两种 session 都扫描（实际只会命中一种）
            turns = []
            for rt in _ROOM_TYPES:
                turns.extend(memory.history_since(f"{rt}:{group_name}", after_id=cursor, limit=_BATCH))
            turns.sort(key=lambda t: t["id"])

            if not turns:
                results[group_id] = 0
                continue

            await export_turns(
                base_url=settings.dify_base_url,
                api_key=settings.dify_dataset_key,
                dataset_id=dataset_id,
                name_prefix=f"群对话_{group_name}",
                turns=turns,
            )
            last_id = turns[-1]["id"]
            store.update_export_cursor(b.get("platform", "wecom"), group_id, last_id)
            results[group_id] = len(turns)
            logger.info(
                "知识库增量导出 group=%s exported=%d last_id=%d",
                group_id, len(turns), last_id,
            )
        except Exception:
            logger.exception("知识库增量导出失败 group=%s", group_id)
            results[group_id] = -1
    return results


async def kb_export_loop(interval: float) -> None:
    """定时循环：每 interval 秒执行一次增量导出；interval<=0 时直接退出（手动导出）。"""
    if interval <= 0:
        logger.info("知识库定时导出未启用（WT_DIFY_EXPORT_INTERVAL<=0），可手动调 POST /api/messages/export")
        return
    logger.info("知识库定时导出启动 interval=%ss", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            if not settings.dify_dataset_key:
                logger.warning("未配置 WT_DIFY_DATASET_KEY，跳过本轮知识库导出")
                continue
            await export_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("知识库定时导出循环异常")
