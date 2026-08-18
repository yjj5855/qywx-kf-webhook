"""回调防抖调度器：按会话合并短时间内的多条消息，只触发一次处理。

背景：WorkTool 用手机辅助功能扫描群聊时，会把短时间内到达的多条不同消息
连续推给回调（1 秒内可能多条）。逐条触发工作流会造成并发调用、重复回复、
上下文错乱。

策略：
- 同一 key（会话 session_id）在窗口内的多条消息合并：只保留最新一条触发
  processor，其余消息由调用方负责先入库（本模块不落库，见 main.py）；
- 窗口内到达 → 合并；处理期间到达 → 串行排队（当前处理完后立即处理最新一条）；
- 同一会话任意时刻最多一个 processor 在执行，杜绝并发工作流调用。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 分组状态表上限，超出后清理空闲项（防止会话字典无限增长）
_MAX_GROUPS = 512


@dataclass
class _GroupState:
    pending: tuple | None = None          # 最新待处理 payload
    task: asyncio.Task | None = None      # 当前调度/执行中的任务
    merged: int = 0                       # 窗口内被合并掉的消息数（仅日志用）


class CallbackDebouncer:
    def __init__(self, window: float, processor) -> None:
        self._window = max(0.0, window)
        self._process = processor          # async callable：processor(*payload)
        self._groups: dict[str, _GroupState] = {}

    def submit(self, key: str, payload: tuple) -> None:
        """投递一条消息：覆盖该会话的 pending（最新），并确保调度任务在跑。"""
        st = self._groups.setdefault(key, _GroupState())
        if st.pending is not None:
            st.merged += 1
        st.pending = payload
        if st.task is None or st.task.done():
            st.task = asyncio.create_task(self._drain(key))
        if len(self._groups) > _MAX_GROUPS:
            self._cleanup()

    def _cleanup(self) -> None:
        for k, v in list(self._groups.items()):
            if v.task is None or v.task.done():
                self._groups.pop(k, None)

    async def _drain(self, key: str) -> None:
        st = self._groups[key]
        try:
            # 防抖窗口：等待窗口结束再开始，窗口内到达的消息合并为最新一条
            await asyncio.sleep(self._window)
            while st.pending is not None:
                payload = st.pending
                st.pending = None
                merged = st.merged
                st.merged = 0
                if merged:
                    logger.debug("防抖合并 key=%s 窗口内消息=%d，仅处理最新一条", key, merged + 1)
                try:
                    await self._process(*payload)
                except Exception:
                    logger.exception("防抖处理失败 key=%r", key)
        except asyncio.CancelledError:
            raise
        finally:
            st.task = None
            # 处理期间又有新消息 → 继续串行处理最新一条
            if st.pending is not None:
                st.task = asyncio.create_task(self._drain(key))
