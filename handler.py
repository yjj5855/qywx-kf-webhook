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
    """意图识别处理器：群聊先经门控判断是否需要回复，再识别意图后路由到对应 Action"""

    def __init__(self) -> None:
        from intent.recognizer import IntentRecognizer
        from intent.actions import AddFriendAction, AddMemberAction, CreateGroupAction
        from intent.types import IntentType
        from intent.gate import GroupReplyGate

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
        self._gate = GroupReplyGate(
            base_url=settings.intent_base_url,
            api_key=settings.intent_api_key,
            model=settings.gate_model or settings.intent_model,
            temperature=settings.gate_temperature,
        )

    async def handle(self, req: CallbackRequest, robot_id: str = "") -> str:
        at_me = req.at_me in (True, "true")
        is_image = req.text_type == 2
        # 图片消息时用占位文本供门控判断，spoken 可能为空
        gate_msg = req.spoken or ("[图片]" if is_image else "")

        # 图片消息：保存到本地并生成外网 URL
        image_url = ""
        image_base64 = ""
        if is_image and req.file_base64:
            from image_utils import save_base64_image

            relative_path = save_base64_image(req.file_base64)
            if relative_path and settings.public_base_url:
                image_url = f"{settings.public_base_url}/static/{relative_path}"
            else:
                image_base64 = req.file_base64  # 无外网地址时用 base64

        # 群聊：未被 @ 时走 AI 门控判断是否需要回复
        if req.is_group and not at_me:
            recent_context = self._recognizer.get_history(req.session_id)
            should_reply = await self._gate.should_reply(
                group_name=req.group_remark or req.group_name,
                sender_name=req.received_name,
                last_message=gate_msg,
                recent_context=recent_context,
            )
            if not should_reply:
                logger.info("门控判定无需回复，跳过")
                return ""

        # 意图识别（带多轮对话记忆 + 上下文 + 图片）
        result = await self._recognizer.recognize(
            spoken=req.spoken,
            session_id=req.session_id,
            user=req.received_name,
            group_name=req.group_remark or req.group_name if req.is_group else "",
            sender_name=req.received_name,
            image_base64=image_base64,
            image_url=image_url,
        )

        logger.info(
            "意图识别结果 intent=%s confidence=%.2f",
            result.intent.value,
            result.confidence,
        )

        # 匹配 Action 执行
        action = self._actions.get(result.intent)
        if action is not None:
            reply = await action.execute(req, result, robot_id)
        else:
            logger.info("未匹配到意图 intent=%s，返回兜底回复", result.intent.value)
            reply = "抱歉，我没理解您的意思，请换个方式描述一下？"

        # 记录对话记忆（图片消息用占位文本）
        user_msg = req.spoken or ("[图片]" if is_image else "")
        self._recognizer.remember(req.session_id, user_msg, reply, req.received_name)
        return reply


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
