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
    """复读机处理器（Demo）：仅回复@机器人的消息"""

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        if req.at_me not in (True, "true"):
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
        from intent.actions import InviteToGroupAction
        from intent.types import IntentType

        self._recognizer = IntentRecognizer(
            base_url=settings.intent_base_url,
            api_key=settings.intent_api_key,
            model=settings.intent_model,
            confidence_threshold=settings.intent_confidence_threshold,
        )
        self._actions: dict[IntentType, InviteToGroupAction] = {
            IntentType.INVITE_TO_GROUP: InviteToGroupAction(),
        }
        self._fallback = EchoHandler()

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        # 仅处理@机器人的消息
        if req.at_me not in (True, "true"):
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
            return await action.execute(req, robot_id)

        # 未匹配：降级到 EchoHandler
        logger.info("未匹配到 Action，降级到 EchoHandler")
        return await self._fallback.handle(req, robot_id)


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
