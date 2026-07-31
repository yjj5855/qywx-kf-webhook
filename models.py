from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


# ---- 回调请求 ----

class CallbackRequest(BaseModel):
    """WorkTool 推送过来的消息"""

    spoken: str = ""
    raw_spoken: str = Field(default="", alias="rawSpoken")
    received_name: str = Field(default="", alias="receivedName")
    group_name: str = Field(default="", alias="groupName")
    group_remark: str = Field(default="", alias="groupRemark")
    room_type: int = Field(default=1, alias="roomType")  # 1=外部群 2=外部联系人 3=内部群 4=内部联系人
    at_me: str | bool = Field(default=False, alias="atMe")
    text_type: int = Field(default=1, alias="textType")
    file_base64: str = Field(default="", alias="fileBase64")
    message_id: str = Field(default="", alias="messageId")

    @property
    def is_group(self) -> bool:
        return self.room_type in (1, 3)

    @property
    def chat_id(self) -> str:
        """会话标识：群聊用 groupRemark，单聊用 receivedName"""
        if self.is_group:
            return self.group_remark or self.group_name
        return self.received_name

    @property
    def session_id(self) -> str:
        """多轮对话唯一标识：room_type + chat_id，全局唯一"""
        return f"{self.room_type}:{self.chat_id}"


# ---- 回调响应（符合官方规范：3 秒内返回） ----

class CallbackResponse(BaseModel):
    code: int = 0
    message: str = "参数接收成功"


# ---- 发送消息 ----

class MessageItem(BaseModel):
    type: int = 203  # 203=文本消息
    title_list: List[str] = Field(default_factory=list, alias="titleList")
    received_content: str = Field(default="", alias="receivedContent")
    at_list: List[str] = Field(default_factory=list, alias="atList")


class SendMessageRequest(BaseModel):
    socket_type: int = Field(default=2, alias="socketType")
    list: List[MessageItem] = Field(default_factory=list)


# ---- 回调配置 ----

class BindCallbackRequest(BaseModel):
    callback_url: str = Field(alias="callbackUrl")
    callback_type: int = Field(default=11, alias="callbackType")  # 11=消息回调
