"""知识库每日定点同步任务 + 手动同步。

对每个绑定了 memory_dataset_id 的群，按 kb_last_export_id 游标增量把
chat_memory 中的真实对话写入群专属 Dify 知识库。

同步策略（不再轮询）：
- 每日北京时间 settings.dify_export_time（默认 23:30）自动同步一次；
- 手动同步：POST /api/messages/sync 调 export_once 立即全量同步；
- 同一逻辑（export_once）两条入口共用。

裁剪策略：导出成功并推进游标后，才删除该群已导出且超出 MAX_TURNS 的旧行
（memory.trim_exported），未导出的行永不删除，保证知识库不丢聊天记录。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.binding import BindingStore
from src.config import settings
from src.kb import export_turns
from src.memory import ChatMemoryStore

logger = logging.getLogger(__name__)

_BATCH = 200  # 每轮每群最多读取的对话条数


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    """解析 HH:MM，非法格式抛 ValueError。"""
    hh, mm = (int(x) for x in hhmm.split(":"))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"非法时间 {hhmm}")
    return hh, mm


def _seconds_until_next_run(hhmm: str, tz_offset_hours: float = 8.0) -> float:
    """距离下一个 hh:mm（东八区北京时间）的等待秒数。

    若目标时间已过则顺延到明天；无夏令时，固定 +8。
    """
    hh, mm = _parse_hhmm(hhmm)
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset_hours)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


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
            # 按群匹配（兼容群备注/群名键不一致，见 memory.history_for_group）
            turns = memory.history_for_group(group_name, after_id=cursor, limit=_BATCH)

            if not turns:
                results[group_id] = 0
                continue

            # 文档名带北京时间日期，避免同名文档无限堆积混淆（如 群对话_测试二群_20260818）
            date_suffix = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y%m%d")
            await export_turns(
                base_url=settings.dify_base_url,
                api_key=settings.dify_dataset_key,
                dataset_id=dataset_id,
                name_prefix=f"群对话_{group_name}_{date_suffix}",
                turns=turns,
            )
            last_id = turns[-1]["id"]
            store.update_export_cursor(b.get("platform", "wecom"), group_id, last_id)
            # 导出成功后再裁剪：只删已导出且超出 MAX_TURNS 的旧行，未导出的保留
            memory.trim_exported(
                session_ids=sorted({t["session_id"] for t in turns}),
                up_to_id=last_id,
            )
            results[group_id] = len(turns)
            logger.info(
                "知识库增量导出 group=%s exported=%d last_id=%d sessions=%s",
                group_id, len(turns), last_id,
                sorted({t["session_id"] for t in turns}),
            )
        except Exception:
            logger.exception("知识库增量导出失败 group=%s", group_id)
            results[group_id] = -1
    return results


async def kb_sync_loop() -> None:
    """每日定点同步循环：北京时间 settings.dify_export_time（默认 23:30）执行一次全量增量导出。

    空串表示关闭定时同步（仅手动调 POST /api/messages/sync）。
    """
    hhmm = (settings.dify_export_time or "").strip()
    if not hhmm:
        logger.info("知识库定时同步未启用（WT_DIFY_EXPORT_TIME 为空），仅支持手动同步")
        return
    try:
        _parse_hhmm(hhmm)
    except ValueError:
        logger.error("WT_DIFY_EXPORT_TIME 格式应为 HH:MM（如 01:00），当前=%r，定时同步已禁用", hhmm)
        return
    logger.info("知识库每日同步启动 time=%s（北京时间）", hhmm)
    while True:
        try:
            wait = _seconds_until_next_run(hhmm)
            logger.info("距离下次知识库同步还有 %.2f 小时", wait / 3600)
            await asyncio.sleep(wait)
            if not settings.dify_dataset_key:
                logger.warning("未配置 WT_DIFY_DATASET_KEY，跳过本轮知识库同步")
                continue
            results = await export_once()
            logger.info("知识库每日同步完成 results=%s", results)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("知识库每日同步循环异常")
