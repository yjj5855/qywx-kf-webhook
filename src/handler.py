from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.config import settings
from src.models import CallbackRequest

logger = logging.getLogger(__name__)


class MessageHandler(ABC):
    """消息处理器基类"""

    @abstractmethod
    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        """处理消息，返回回复文本。空字符串表示不回复。"""
        ...


class EchoHandler(MessageHandler):
    """复读机处理器（兜底）：群聊仅回复@消息，私聊全部回复"""

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        if req.is_group and req.at_me not in (True, "true"):
            return ""
        return req.spoken


class DifyWorkflowHandler(MessageHandler):
    """Dify 主工作流处理器：接收回调整理参数 → 调用主工作流 → 处理公司查询 action。

    职责边界：
    - 把回调字段整理成主工作流 start 节点的 inputs，调用 /v1/workflows/run；
    - 持久化返回的 conversationId / qaConversationId（按 session_id）；
    - 问答/操作/追问等路径的回复由主工作流内部通过 WorkTool 直接发送，本处理器不再重复回复；
    - 仅当返回 action=company_info_query 时，由应用层用群绑定 company_ids 调公司接口并回复。
    """

    PLATFORM = "wecom"  # WorkTool = 企业微信

    def __init__(self) -> None:
        from src.binding import BindingStore
        from src.company import build_company_provider
        from src.dify_client import DifyWorkflowClient
        from src.memory import ChatMemoryStore
        from src.session_store import SessionStore

        self._dify = DifyWorkflowClient(
            base_url=settings.dify_base_url,
            api_key=settings.dify_workflow_key,
            timeout=settings.dify_timeout,
        )
        self._sessions = SessionStore(settings.dify_db_path)
        self._bindings = BindingStore(settings.dify_db_path)
        self._memory = ChatMemoryStore(settings.dify_db_path)
        self._company = build_company_provider()

    def _build_inputs(self, req: CallbackRequest, convo: dict) -> dict:
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
            "qaConversationId": convo.get("qa_conversation_id", ""),
            # 最近几轮真实对话（用户消息 + 机器人回复），由主工作流注入意图识别 LLM 的上下文
            "recentContext": self._memory.to_context(req.session_id),
        }

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        session_id = req.session_id
        convo = self._sessions.get(session_id)
        user_msg = req.spoken or ("[图片]" if req.text_type == 2 else "")

        try:
            outputs = await self._dify.run_workflow(
                inputs=self._build_inputs(req, convo),
                user=session_id,
            )
        except Exception as exc:
            logger.exception("调用 Dify 主工作流失败 session=%r", session_id)
            return f"抱歉，服务暂时不可用，请稍后再试。（{type(exc).__name__}）"

        # 持久化 QA Chatflow 会话 ID（意图识别已改为工作流内普通 LLM，无需 conversationId）
        qa_id = (outputs.get("qaConversationId") or "").strip()
        if qa_id:
            self._sessions.set(session_id, "", qa_id)

        # 公司信息查询：工作流不发消息，由应用层用群绑定 company_ids 调公司接口并回复
        if outputs.get("action") == "company_info_query":
            reply = await self._handle_company_query(req, outputs)
            if reply:
                self._memory.append(session_id, user_msg, reply, req.received_name)
            return reply

        # 其余路径（问答/操作/追问）的回复由主工作流内部发送，这里把 (用户消息, 最终回复)
        # 记入服务端记忆，供下轮意图分类注入上下文（Dify 不支持改写聊天记录的历史会话）
        final_text = (outputs.get("final_text") or "").strip()
        if final_text:
            self._memory.append(session_id, user_msg, final_text, req.received_name)
        logger.info("Dify 工作流已处理 session=%r outputs=%s", session_id, outputs)
        return ""

    async def _handle_company_query(self, req: CallbackRequest, outputs: dict) -> str:
        # 回调只有群名，按群名反查绑定（group_id 为 G 编码稳定标识）
        binding = self._bindings.get_by_group_name(self.PLATFORM, req.chat_id)
        if binding is None:
            logger.warning("群未绑定公司或群名重名 company_query chat_id=%r", req.chat_id)
            return "该群未绑定公司信息（或群名存在重名），请联系管理员处理后重试。"
        company_ids = self._bindings.get_company_ids(self.PLATFORM, binding["group_id"])
        if not company_ids:
            logger.warning("群未绑定公司 company_query chat_id=%r", req.chat_id)
            return "该群未绑定公司信息，无法查询公司数据，请联系管理员绑定。"
        try:
            return await self._company.query(
                company_ids=company_ids,
                query_type=outputs.get("query_type", ""),
                keyword=outputs.get("keyword", ""),
                period=outputs.get("period", ""),
            )
        except Exception:
            logger.exception("公司信息查询失败 chat_id=%r", req.chat_id)
            return "公司信息查询失败，请稍后再试或联系管理员。"


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
