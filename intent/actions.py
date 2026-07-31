from __future__ import annotations

from abc import ABC, abstractmethod

from intent.types import IntentType
from models import CallbackRequest


class IntentAction(ABC):
    """意图处理器抽象基类，每个意图对应一个 Action"""

    intent_type: IntentType

    @abstractmethod
    async def execute(self, req: CallbackRequest, robot_id: str = "") -> str:
        """执行意图对应的业务逻辑，返回回复文本。空字符串表示不回复。"""
        ...


class InviteToGroupAction(IntentAction):
    """拉人入群意图处理器"""

    intent_type = IntentType.INVITE_TO_GROUP

    async def execute(self, req: CallbackRequest, robot_id: str = "") -> str:
        spoken = req.spoken.strip()
        received_name = req.received_name or "用户"

        # 提取可能的群名（简单启发式：取消息末尾可能的目标群名）
        target_group = _extract_group_name(spoken)

        if req.is_group and target_group:
            return f"收到，正在为您邀请 {received_name} 加入群「{target_group}」，请稍候..."
        elif target_group:
            return f"收到，请将 {received_name} 的微信号或企微名片发给我，我来帮您拉入群「{target_group}」"
        else:
            return (
                f"收到，请问您需要邀请谁加入哪个群呢？\n"
                f"请描述：需要拉的人 + 目标群名"
            )


def _extract_group_name(spoken: str) -> str:
    """从消息文本中提取目标群名（简单启发式）"""
    import re

    # 匹配"到XX群""加入XX群""拉进XX群"等模式
    patterns = [
        r"[到进拉入至].*?[「『](.+?)[」』]",
        r"[到进拉入至]\s*(.+?)(?:群|$)",
    ]
    for pat in patterns:
        m = re.search(pat, spoken)
        if m:
            name = m.group(1).strip()
            if name and len(name) < 20:
                return name
    return ""
