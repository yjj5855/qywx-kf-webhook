from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """用户消息意图类型"""

    CREATE_GROUP = "CREATE_GROUP"  # 创建新群
    ADD_MEMBER = "ADD_MEMBER"  # 拉人进已有群
    ADD_FRIEND = "ADD_FRIEND"  # 按手机号添加好友
    UNKNOWN = "UNKNOWN"  # 未识别


class IntentResult(BaseModel):
    """意图识别结果"""

    intent: IntentType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_answer: str = ""
    entities: dict = Field(default_factory=dict)


@dataclass
class IntentMeta:
    """意图元信息，作为门控、识别器等模块的统一配置来源"""

    chinese_name: str  # 中文名称，如"建群"
    description: str  # 简要描述，用于 AI 提示词
    examples: list[str] = field(default_factory=list)  # 用户消息示例
    keywords: list[str] = field(default_factory=list)  # 关键词，用于 fallback 文本匹配

    @property
    def prompt_line(self) -> str:
        """生成提示词中使用的单行描述，例如：CREATE_GROUP: 创建新群。如"建群""帮我建个群拉上张三李四"。"""
        examples_str = "".join(f'"{e}"' for e in self.examples)
        return f"{self.chinese_name}。如{examples_str}。"


# 意图元信息统一配置
INTENT_META: dict[IntentType, IntentMeta] = {
    IntentType.CREATE_GROUP: IntentMeta(
        chinese_name="建群",
        description="创建新群",
        examples=["建群", "创建一个群", "新建一个XX群", "帮我建个群拉上张三李四"],
        keywords=["建群", "创建群", "新建群"],
    ),
    IntentType.ADD_MEMBER: IntentMeta(
        chinese_name="拉人进群",
        description="往已有群拉人",
        examples=["拉群", "拉我进群", "把XX拉进产品群", "把XX加到群里"],
        keywords=["拉人入群", "拉人", "拉群", "邀请入群"],
    ),
    IntentType.ADD_FRIEND: IntentMeta(
        chinese_name="添加好友",
        description="按手机号添加好友",
        examples=["加好友", "加这个手机号", "帮我加个人"],
        keywords=["加好友", "添加好友"],
    ),
}
