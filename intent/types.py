from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """用户消息意图类型"""

    INVITE_TO_GROUP = "INVITE_TO_GROUP"  # 拉人入群
    UNKNOWN = "UNKNOWN"  # 未识别


class IntentResult(BaseModel):
    """意图识别结果"""

    intent: IntentType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_answer: str = ""
