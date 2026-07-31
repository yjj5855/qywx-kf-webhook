from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from config import settings
from models import CallbackRequest

logger = logging.getLogger(__name__)


class MessageHandler(ABC):
    """消息处理器基类"""

    @abstractmethod
    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        """处理消息，返回回复文本。空字符串表示不回复。"""
        ...


class EchoHandler(MessageHandler):
    """复读机处理器（Demo）：群聊仅回复@消息，私聊全部回复"""

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        if req.is_group and req.at_me not in (True, "true"):
            return ""
        return req.spoken


class SilentHandler(MessageHandler):
    """静默处理器：不回复任何消息"""

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        return ""


class IntentHandler(MessageHandler):
    """意图识别处理器：识别意图后路由到对应 Action"""

    def __init__(self) -> None:
        from intent.recognizer import IntentRecognizer
        from intent.actions import AddFriendAction, AddMemberAction, CreateGroupAction
        from intent.types import IntentType

        self._recognizer = IntentRecognizer(
            base_url=settings.intent_base_url,
            api_key=settings.intent_api_key,
            model=settings.intent_model,
            temperature=settings.intent_temperature,
            confidence_threshold=settings.intent_confidence_threshold,
        )
        self._actions: dict[IntentType, AddFriendAction | AddMemberAction | CreateGroupAction] = {
            IntentType.ADD_FRIEND: AddFriendAction(),
            IntentType.ADD_MEMBER: AddMemberAction(),
            IntentType.CREATE_GROUP: CreateGroupAction(),
        }
    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        # 群聊仅处理@机器人的消息，私聊全部处理
        if req.is_group and req.at_me not in (True, "true"):
            return ""

        # 意图识别（带多轮对话记忆）
        result = await self._recognizer.recognize(
            spoken=req.spoken,
            session_id=req.session_id,
            user=req.received_name,
        )

        logger.info(
            "意图识别结果 intent=%s confidence=%.2f",
            result.intent.value,
            result.confidence,
        )

        # 匹配 Action 执行
        action = self._actions.get(result.intent)
        if action is not None:
            return await action.execute(req, result, robot_id)

        # 意图识别失败：告知用户
        logger.info("意图识别失败 intent=%s，返回提示", result.intent.value)
        return "抱歉，我没理解您的意思，请换个方式描述一下？"


# ---- 全局处理器 ----

def _build_default_handler() -> MessageHandler:
    """根据配置构建默认处理器"""
    if settings.intent_base_url:
        logger.info("启用意图识别处理器")
        return IntentHandler()
    logger.info("未配置意图识别 API，使用 EchoHandler")
    return EchoHandler()


_handler: MessageHandler = _build_default_handler()


def get_handler(robot_id: str = "") -> MessageHandler:
    return _handler


def set_handler(handler: MessageHandler) -> None:
    global _handler
    _handler = handler
