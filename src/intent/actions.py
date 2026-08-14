from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from src.intent.types import IntentResult, IntentType
from src.models import CallbackRequest

logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"1[3-9]\d{9}")


def _extract_phone(text: str) -> str:
    """从文本中提取手机号"""
    m = _PHONE_RE.search(text)
    return m.group(0) if m else ""


class IntentAction(ABC):
    """意图处理器抽象基类，每个意图对应一个 Action"""

    intent_type: IntentType

    @abstractmethod
    async def execute(self, req: CallbackRequest, result: IntentResult, robot_id: str = "") -> str:
        """执行意图对应的业务逻辑，返回回复文本。空字符串表示不回复。"""
        ...


class AddFriendAction(IntentAction):
    """按手机号添加好友意图处理器"""

    intent_type = IntentType.ADD_FRIEND

    async def execute(self, req: CallbackRequest, result: IntentResult, robot_id: str = "") -> str:
        entities = result.entities
        target_phone = entities.get("target_phone", "")
        target_person = entities.get("target_person", "")

        # 从 spoken 中提取手机号作为兜底
        if not target_phone:
            target_phone = _extract_phone(req.spoken)

        if not target_phone:
            return "请问要添加的好友手机号是多少？"

        try:
            from client import get_client

            client = get_client(robot_id)
            mark_name = target_person or target_phone
            resp = await client.add_friend_by_phone(
                phone=target_phone,
                mark_name=mark_name,
                leaving_msg="你好，我是机器人助理~",
            )
            logger.info("添加好友成功 phone=%s mark=%s result=%s", target_phone, mark_name, resp)
            return f"已发送好友申请给 {mark_name}（{target_phone}），请等待对方通过。"
        except Exception:
            logger.exception("添加好友失败")
            return f"添加好友 {target_phone} 失败，请稍后重试。"


async def _add_friends_first(robot_id: str, members: list[str]) -> list[str]:
    """先对含手机号的成员发起好友申请，返回已申请的成员列表"""
    from client import get_client

    client = get_client(robot_id)
    added: list[str] = []
    for member in members:
        phone = _extract_phone(member)
        if phone:
            try:
                await client.add_friend_by_phone(
                    phone=phone,
                    mark_name=member.replace(phone, "").strip() or phone,
                    leaving_msg="你好，拉你进群~",
                )
                added.append(member)
                logger.info("已发送好友申请 %s", member)
            except Exception:
                logger.exception("添加好友失败 %s", member)
    return added


class AddMemberAction(IntentAction):
    """拉人进已有群意图处理器（type=207）"""

    intent_type = IntentType.ADD_MEMBER

    async def execute(self, req: CallbackRequest, result: IntentResult, robot_id: str = "") -> str:
        entities = result.entities
        target_person = entities.get("target_person", "")
        target_group = entities.get("target_group", "")

        # 私聊中"拉群""拉我" → 用户自己想进群
        if not req.is_group and target_person in ("", "我"):
            target_person = req.received_name or "您"

        # 群聊中没指定人 → 需要问清楚
        if req.is_group and not target_person:
            return "请问需要邀请谁加入群呢？请提供姓名、手机号或微信号。"

        # 没指定目标群 → 需要问清楚
        if not target_group:
            members_str = f"（成员：{target_person}）" if target_person else ""
            return f"收到，请问要拉到哪个群呢？{members_str}"

        # 解析成员列表
        members = [m.strip() for m in target_person.replace("、", ",").split(",") if m.strip()]
        if req.received_name and req.received_name not in members and not req.is_group:
            members.insert(0, req.received_name)

        try:
            # 先加好友
            added = await _add_friends_first(robot_id, members)
            # 拉人进已有群（type=207）
            from client import get_client

            client = get_client(robot_id)
            resp = await client.update_group(group_name=target_group, add_members=members)
            logger.info("拉人成功 group=%r members=%s result=%s", target_group, members, resp)

            if added:
                return f"已向 {', '.join(added)} 发送好友申请，通过后自动拉入群「{target_group}」！"
            return f"已将 {', '.join(members)} 拉入群「{target_group}」！"
        except Exception:
            logger.exception("拉人失败")
            return f"拉人进群「{target_group}」失败，请稍后重试。"


class CreateGroupAction(IntentAction):
    """创建新群意图处理器（type=206）"""

    intent_type = IntentType.CREATE_GROUP

    async def execute(self, req: CallbackRequest, result: IntentResult, robot_id: str = "") -> str:
        entities = result.entities
        target_person = entities.get("target_person", "")
        target_group = entities.get("target_group", "")

        # 私聊中"建群" → 用户自己也要在群里
        if not req.is_group and target_person in ("", "我"):
            target_person = req.received_name or "您"

        # 没指定群名 → 需要问清楚
        if not target_group:
            members_str = f"（成员：{target_person}）" if target_person else ""
            return f"收到，请问新群叫什么名字呢？{members_str}"

        # 解析成员列表
        members = [m.strip() for m in target_person.replace("、", ",").split(",") if m.strip()]
        if req.received_name and req.received_name not in members:
            members.insert(0, req.received_name)

        try:
            # 先加好友
            added = await _add_friends_first(robot_id, members)
            # 建群（type=206）
            from client import get_client

            client = get_client(robot_id)
            resp = await client.create_group(group_name=target_group, members=members)
            logger.info("建群成功 group=%r members=%s result=%s", target_group, members, resp)

            if added:
                return f"已创建群「{target_group}」，已向 {', '.join(added)} 发送好友申请，通过后自动拉入群！"
            return f"已创建群「{target_group}」并邀请 {', '.join(members)} 加入！"
        except Exception:
            logger.exception("建群失败")
            return f"创建群「{target_group}」失败，请稍后重试。"
