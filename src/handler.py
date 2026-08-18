from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.config import settings
from src.models import CallbackRequest

logger = logging.getLogger(__name__)


@dataclass
class HandleResult:
    """消息处理结果，供上层决定是否由 webhook 发送回复。

    - reply_text 非空：需要 webhook 主动发送（如公司查询路径）；
    - sent_internally=True：回复已由主工作流内部直接发到群里，webhook 不重复发送；
    - 两者皆空：本次不产生回复（如门控跳过），reason 说明原因。
    """

    reply_text: str = ""
    sent_internally: bool = False
    reason: str = ""


def _extract_reply_text(value: str) -> str:
    """从工作流 final_text 中提取纯文本回复。

    新版 Dify 结束节点可能输出形如 {"reply_text": "..."} 的 JSON 字符串，
    这里兼容解包；解不开则原样返回。
    """
    text = (value or "").strip()
    if not text:
        return ""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    if isinstance(obj, dict):
        for key in ("reply_text", "answer", "text", "final_text"):
            if obj.get(key):
                return str(obj[key]).strip()
    return text


class MessageHandler(ABC):
    """消息处理器基类"""

    @abstractmethod
    async def handle(self, req: CallbackRequest, robot_id: str = "") -> HandleResult:
        """处理消息，返回处理结果（回复文本 + 发送方式说明）。"""
        ...


class EchoHandler(MessageHandler):
    """复读机处理器（兜底）：群聊仅回复@消息，私聊全部回复"""

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> HandleResult:
        if req.is_group and req.at_me not in (True, "true"):
            return HandleResult(reason="群聊未@，不回复")
        return HandleResult(reply_text=req.spoken, reason="复读机兜底")


class DifyWorkflowHandler(MessageHandler):
    """Dify 主工作流处理器：接收回调 → 整理参数 → 调用主工作流 → 记录群聊记录。

    职责边界（当前分工）：
    - 把回调字段整理成主工作流 start 节点的 inputs，调用 /v1/workflows/run；
    - 问答/操作/公司查询等所有意图的回复均由主工作流内部通过 WorkTool 直接发送，
      本处理器不再重复回复，也不在应用层执行公司查询；
    - 主工作流返回 final_text（最终发送的文本）时，写入群聊记录库（chat_memory）供知识库导出；
    - 多轮上下文由群聊记录库提供：recentContext 注入主工作流用于意图分类；
    - 不再持久化/透传 Dify 的 qaConversationId（会话由工作流侧自行管理）。
    """

    PLATFORM = "wecom"  # WorkTool = 企业微信

    def __init__(self) -> None:
        from src.binding import BindingStore
        from src.dify_client import DifyWorkflowClient
        from src.memory import ChatMemoryStore

        self._dify = DifyWorkflowClient(
            base_url=settings.dify_base_url,
            api_key=settings.dify_workflow_key,
            timeout=settings.dify_timeout,
        )
        self._bindings = BindingStore(settings.dify_db_path)
        self._memory = ChatMemoryStore(settings.dify_db_path)

    def _resolve_company_ids(self, req: CallbackRequest) -> str:
        """按群名反查绑定，取群绑定的公司 ID（顿号分隔字符串，如 "1001、1002"）。

        非群聊或无绑定返回空串，工作流侧需自行处理空值。
        """
        if not req.is_group:
            return ""
        binding = self._bindings.get_by_group_name(self.PLATFORM, req.chat_id)
        if binding is None:
            return ""
        return binding.get("company_ids") or ""

    def _build_inputs(self, req: CallbackRequest) -> dict:
        return {
            "spoken": req.spoken,
            "rawSpoken": req.raw_spoken,
            "receivedName": req.received_name,
            "groupName": req.group_name,
            "groupRemark": req.group_remark,
            "roomType": req.room_type,
            "atMe": req.at_me in (True, "true"),
            "textType": req.text_type,
            # Dify 侧 start 输入限长 256，且当前意图链路不消费图片内容，仅透传占位
            "fileBase64": req.file_base64[:256],
            "messageId": req.message_id,
            # 最近几轮真实对话（用户消息 + 机器人回复），由主工作流注入意图识别 LLM 的上下文
            "recentContext": self._memory.to_context(req.session_id),
            # 群绑定的公司 ID（顿号分隔），供主工作流内部路由/公司查询使用
            "companyIds": self._resolve_company_ids(req),
        }

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> HandleResult:
        session_id = req.session_id
        user_msg = req.spoken or ("[图片]" if req.text_type == 2 else "")

        try:
            outputs = await self._dify.run_workflow(
                inputs=self._build_inputs(req),
                user=session_id,
            )
        except Exception as exc:
            logger.exception("调用 Dify 主工作流失败 session=%r", session_id)
            # 失败时不回复客户：blocking 调用超时并不代表工作流未执行，
            # 若此时再发兜底文案，可能与工作流迟到的真实回复重复；只记日志。
            return HandleResult(
                reason=f"Dify 主工作流调用失败（{type(exc).__name__}），不回复客户",
            )

        # 主工作流返回 final_text（最终发送到群里的文本）→ 写入群聊记录库，供知识库导出
        final_text = _extract_reply_text(outputs.get("final_text") or "")
        if final_text:
            self._memory.append(session_id, user_msg, final_text, req.received_name)
        logger.info("Dify 工作流已处理 session=%r outputs=%s", session_id, outputs)
        if final_text:
            return HandleResult(
                sent_internally=True,
                reason="回复已由主工作流内部直接发送，webhook 不重复发送",
            )
        return HandleResult(reason="主工作流未产生回复（门控跳过或无输出）")


# ---- 全局处理器 ----

def _build_default_handler() -> MessageHandler:
    """根据配置构建默认处理器（优先 Dify 主工作流，未配置则用 Echo 兜底）"""
    if settings.dify_base_url and settings.dify_workflow_key:
        logger.info("启用 Dify 主工作流处理器")
        return DifyWorkflowHandler()
    logger.info("未配置 Dify 主工作流，使用 EchoHandler")
    return EchoHandler()


_handler: MessageHandler = _build_default_handler()


def get_handler(robot_id: str = "") -> MessageHandler:
    return _handler
