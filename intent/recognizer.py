from __future__ import annotations

import logging
from collections import defaultdict

from openai import AsyncOpenAI

from intent.types import IntentResult, IntentType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个消息意图识别助手。分析用户消息，结合对话上下文判断意图并提取关键实体。

## 支持的意图
- ADD_FRIEND: 添加好友。如"加好友""加这个手机号""帮我加个人"。
- CREATE_GROUP: 创建新群。如"建群""创建一个群""新建一个XX群""帮我建个群拉上张三李四"。
- ADD_MEMBER: 往已有群拉人。如"拉群""拉我进群""把XX拉进产品群""把XX加到群里"。

## 实体提取
针对 ADD_FRIEND：
- target_phone: 手机号（纯数字）
- target_person: 姓名/昵称（备注用，不知道留空）

针对 CREATE_GROUP / ADD_MEMBER：
- target_person: 要拉入群的人（姓名/手机号，多人用中文顿号分隔），说"拉我"则是"我"
- target_group: 目标群名（不知道的留空）

## 输出格式
只返回一个 JSON 对象：
{"intent": "<意图>", "confidence": <0.0-1.0>, "target_person": "", "target_group": "", "target_phone": ""}

无法识别时返回：
{"intent": "UNKNOWN", "confidence": 0.0}"""

MAX_HISTORY = 10  # 每个会话最多保留的消息数（5 轮对话）


class ConversationMemory:
    """会话记忆，按 session_id 存储对话历史"""

    def __init__(self, max_messages: int = MAX_HISTORY) -> None:
        self._store: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._max_messages = max_messages

    def get(self, session_id: str) -> list[dict[str, str]]:
        return list(self._store.get(session_id, []))

    def add(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        history = self._store[session_id]
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        if len(history) > self._max_messages:
            self._store[session_id] = history[-self._max_messages:]

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


class IntentRecognizer:
    """意图识别器，使用 OpenAI 兼容的 API 格式调用 AI 服务"""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._confidence_threshold = confidence_threshold
        self._memory = ConversationMemory()
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI | None:
        if not self._base_url:
            return None
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key or "sk-placeholder",
                base_url=self._base_url,
                timeout=60.0,
            )
        return self._client

    async def recognize(self, spoken: str, session_id: str = "", user: str = "") -> IntentResult:
        """识别用户消息意图

        Args:
            spoken: 用户问题文本
            session_id: 会话唯一标识，用于多轮对话记忆
            user: 用户标识

        Returns:
            IntentResult：识别结果；异常或未配置时降级为 UNKNOWN
        """
        client = self._get_client()
        if client is None:
            logger.info("未配置 intent_base_url，跳过意图识别")
            return IntentResult(intent=IntentType.UNKNOWN)

        try:
            messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
            if session_id:
                messages.extend(self._memory.get(session_id))
            messages.append({"role": "user", "content": spoken})

            logger.info(
                "意图识别请求 session=%r msg_count=%d spoken=%r",
                session_id,
                len(messages),
                spoken[:50],
            )

            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                stream=False,
            )

            answer = response.choices[0].message.content or ""
            intent, confidence, entities = self._parse_answer(answer)

            if session_id:
                self._memory.add(session_id, spoken, answer)

            logger.info(
                "意图识别完成 session=%r intent=%s confidence=%.2f entities=%s",
                session_id,
                intent.value,
                confidence,
                entities,
            )

            if confidence < self._confidence_threshold:
                logger.info(
                    "置信度 %.2f 低于阈值 %.2f，降级为 UNKNOWN",
                    confidence,
                    self._confidence_threshold,
                )
                return IntentResult(intent=IntentType.UNKNOWN, confidence=confidence, raw_answer=answer)

            return IntentResult(intent=intent, confidence=confidence, raw_answer=answer, entities=entities)

        except Exception:
            logger.exception("意图识别失败，降级为 UNKNOWN")
            return IntentResult(intent=IntentType.UNKNOWN)

    def _parse_answer(self, answer: str) -> tuple[IntentType, float, dict]:
        """从 AI 回答中解析意图、置信度和实体

        支持格式：
        - JSON: {"intent": "INVITE_TO_GROUP", "confidence": 0.95, "target_person": "张三", "target_group": "产品群"}
        - 纯文本: "INVITE_TO_GROUP" 或 "UNKNOWN"
        """
        try:
            import json

            data = json.loads(answer.strip())
            if isinstance(data, dict):
                intent_str = str(data.get("intent", "")).upper().strip()
                confidence = float(data.get("confidence", 0.9))
                entities = {
                    k: str(data.get(k, ""))
                    for k in ("target_person", "target_group", "target_phone")
                }
                return (
                    _str_to_intent(intent_str),
                    min(max(confidence, 0.0), 1.0),
                    entities,
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        cleaned = answer.strip().upper()
        intent = _str_to_intent(cleaned)
        confidence = 0.9 if intent != IntentType.UNKNOWN else 0.0
        return intent, confidence, {}


def _str_to_intent(text: str) -> IntentType:
    """字符串到意图类型的宽松映射"""
    mapping: dict[str, IntentType] = {
        "ADD_FRIEND": IntentType.ADD_FRIEND,
        "ADD_MEMBER": IntentType.ADD_MEMBER,
        "CREATE_GROUP": IntentType.CREATE_GROUP,
        "INVITE_TO_GROUP": IntentType.ADD_MEMBER,
        "建群": IntentType.CREATE_GROUP,
        "创建群": IntentType.CREATE_GROUP,
        "新建群": IntentType.CREATE_GROUP,
        "拉人入群": IntentType.ADD_MEMBER,
        "拉人": IntentType.ADD_MEMBER,
        "拉群": IntentType.ADD_MEMBER,
        "邀请入群": IntentType.ADD_MEMBER,
        "加好友": IntentType.ADD_FRIEND,
        "添加好友": IntentType.ADD_FRIEND,
        "INVITE": IntentType.ADD_MEMBER,
    }
    for key, intent in mapping.items():
        if key in text:
            return intent
    return IntentType.UNKNOWN
