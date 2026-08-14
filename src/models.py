from __future__ import annotations

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

    _ROOM_TYPE_MAP: dict[int, str] = {
        1: "外部群",
        2: "外部联系人",
        3: "内部群",
        4: "内部联系人",
    }

    @property
    def scene(self) -> str:
        """场景描述"""
        return self._ROOM_TYPE_MAP.get(self.room_type, f"未知({self.room_type})")

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


# ---- 群绑定管理（公司信息查询/知识库用） ----

class BindingItem(BaseModel):
    platform: str = "wecom"      # 群平台：wecom/feishu/dingtalk
    group_id: str                # 群标识（群备注名优先，无则群名）
    group_name: str = ""         # 群名称
    company_ids: str = ""        # 公司ID列表，顿号分隔（兼容逗号/分号），如 "1001、1002"
    workflow_app_id: str = ""    # 预留：Dify 客服 Workflow 应用 ID
    memory_dataset_id: str = ""  # 群专属 Dify 知识库 ID（群聊天记录导出用）
