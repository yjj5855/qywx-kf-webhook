from __future__ import annotations

import logging
from collections import defaultdict

from openai import AsyncOpenAI

from intent.types import IntentResult, IntentType, INTENT_META

logger = logging.getLogger(__name__)

# ---- 系统提示词（意图列表从 INTENT_META 动态生成） ----

_INTENT_LINES = "\n".join(
    f"- {intent.value}: {meta.prompt_line}"
    for intent, meta in INTENT_META.items()
    if intent != IntentType.UNKNOWN
)

SYSTEM_PROMPT = f"""你是一个消息意图识别助手。分析用户消息，结合对话上下文判断意图并提取关键实体。

## 支持的意图
{_INTENT_LINES}

## 实体提取
针对 ADD_FRIEND：
- target_phone: 手机号（纯数字）
- target_person: 姓名/昵称（备注用，不知道留空）

针对 CREATE_GROUP / ADD_MEMBER：
- target_person: 要拉入群的人（姓名/手机号，多人用中文顿号分隔），说"拉我"则是"我"
- target_group: 目标群名（不知道的留空）

## 输出格式
只返回一个 JSON 对象：
{{"intent": "<意图>", "confidence": <0.0-1.0>, "target_person": "", "target_group": "", "target_phone": ""}}

无法识别时返回：
{{"intent": "UNKNOWN", "confidence": 0.0}}"""

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

    def get_history(self, session_id: str) -> str:
        """获取会话历史，格式化为门控可用的上下文字符串"""
        history = self._memory.get(session_id)
        if not history:
            return ""
        lines: list[str] = []
        for msg in history:
            role_label = "用户" if msg["role"] == "user" else "机器人"
            lines.append(f"{role_label}：{msg['content']}")
        return "\n".join(lines)

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
            logger.debug("意图识别 OpenAI 请求体 messages=%s", messages)

            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                stream=False,
            )

            answer = response.choices[0].message.content or ""
            logger.info("意图识别 OpenAI 返回 raw_answer=%r", answer)
            logger.debug("意图识别 OpenAI 返回体 raw=%s", response)
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


# 关键词到意图的映射（从 INTENT_META + 英文枚举名构建）
_KEYWORD_MAPPING: dict[str, IntentType] = {}
for _intent, _meta in INTENT_META.items():
    if _intent == IntentType.UNKNOWN:
        continue
    # 英文枚举名和变体
    _KEYWORD_MAPPING[_intent.value] = _intent
    # 中文关键词
    for _kw in _meta.keywords:
        _KEYWORD_MAPPING[_kw] = _intent
# 历史兼容的英文别名
_KEYWORD_MAPPING["INVITE_TO_GROUP"] = IntentType.ADD_MEMBER
_KEYWORD_MAPPING["INVITE"] = IntentType.ADD_MEMBER


def _str_to_intent(text: str) -> IntentType:
    """字符串到意图类型的宽松映射"""
    for key, intent in _KEYWORD_MAPPING.items():
        if key in text:
            return intent
    return IntentType.UNKNOWN
