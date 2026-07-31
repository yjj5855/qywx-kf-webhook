from __future__ import annotations

import logging
from collections import defaultdict

from openai import AsyncOpenAI

from intent.types import IntentResult, IntentType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个消息意图识别助手。分析用户消息，结合对话上下文判断意图并返回 JSON。

## 支持的意图
- INVITE_TO_GROUP: 用户想邀请/拉人进入某个群聊

## 输出格式
只返回一个 JSON 对象，不要有其他内容：
{"intent": "<意图>", "confidence": <0.0-1.0的置信度>}

如果无法识别意图，返回：
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
        confidence_threshold: float = 0.7,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
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
                timeout=10.0,
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
                temperature=0.1,
            )

            answer = response.choices[0].message.content or ""
            intent, confidence = self._parse_answer(answer)

            if session_id:
                self._memory.add(session_id, spoken, answer)

            logger.info(
                "意图识别完成 session=%r intent=%s confidence=%.2f raw=%r",
                session_id,
                intent.value,
                confidence,
                answer[:100],
            )

            if confidence < self._confidence_threshold:
                logger.info(
                    "置信度 %.2f 低于阈值 %.2f，降级为 UNKNOWN",
                    confidence,
                    self._confidence_threshold,
                )
                return IntentResult(intent=IntentType.UNKNOWN, confidence=confidence, raw_answer=answer)

            return IntentResult(intent=intent, confidence=confidence, raw_answer=answer)

        except Exception:
            logger.exception("意图识别失败，降级为 UNKNOWN")
            return IntentResult(intent=IntentType.UNKNOWN)

    def _parse_answer(self, answer: str) -> tuple[IntentType, float]:
        """从 AI 回答中解析意图和置信度

        支持格式：
        - JSON: {"intent": "INVITE_TO_GROUP", "confidence": 0.95}
        - 纯文本: "INVITE_TO_GROUP" 或 "UNKNOWN"
        """
        try:
            import json

            data = json.loads(answer.strip())
            if isinstance(data, dict):
                intent_str = str(data.get("intent", "")).upper().strip()
                confidence = float(data.get("confidence", 0.9))
                return _str_to_intent(intent_str), min(max(confidence, 0.0), 1.0)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        cleaned = answer.strip().upper()
        intent = _str_to_intent(cleaned)
        confidence = 0.9 if intent != IntentType.UNKNOWN else 0.0
        return intent, confidence


def _str_to_intent(text: str) -> IntentType:
    """字符串到意图类型的宽松映射"""
    mapping: dict[str, IntentType] = {
        "INVITE_TO_GROUP": IntentType.INVITE_TO_GROUP,
        "INVITE": IntentType.INVITE_TO_GROUP,
        "拉人入群": IntentType.INVITE_TO_GROUP,
        "拉人": IntentType.INVITE_TO_GROUP,
        "邀请入群": IntentType.INVITE_TO_GROUP,
    }
    for key, intent in mapping.items():
        if key in text:
            return intent
    return IntentType.UNKNOWN
