from __future__ import annotations

from abc import ABC, abstractmethod

from models import CallbackRequest


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


# 默认使用复读机处理器
_handler: MessageHandler = EchoHandler()


def get_handler(robot_id: str = "") -> MessageHandler:
    return _handler


def set_handler(handler: MessageHandler) -> None:
    global _handler
    _handler = handler
