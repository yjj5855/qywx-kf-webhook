from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

GATE_SYSTEM_PROMPT = """\
你是群聊回复门控器。请判断最后一条消息是否应由机器人在群聊公开回复。
规则：如果最后一条是在问机器人问题，或者是售前售后咨询/功能答疑/问题排查，则返回 YES；
如果更像成员间闲聊、互相对话、与机器人无关，则返回 NO。
只允许输出 YES 或 NO，不要输出其他任何文字。"""


class GroupReplyGate:
    """群聊回复门控器：使用 AI 判断群聊消息是否需要机器人公开回复。

    在意图识别之前调用，若门控判定为 NO 则跳过后续处理，节省成本并避免骚扰。
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI | None:
        if not self._base_url:
            return None
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key or "sk-placeholder",
                base_url=self._base_url,
                timeout=30.0,
            )
        return self._client

    async def should_reply(
        self,
        group_name: str,
        sender_name: str,
        last_message: str,
        recent_context: str = "",
    ) -> bool:
        """判断群聊消息是否需要机器人回复。

        Args:
            group_name: 群名
            sender_name: 发送者名称
            last_message: 最后一条消息内容
            recent_context: 近期对话上下文

        Returns:
            True 表示应该回复，False 表示不应回复。
            AI 不可用时默认放行（fail-open）。
        """
        client = self._get_client()
        if client is None:
            logger.info("门控未配置 AI API，默认放行")
            return True

        try:
            user_prompt = f"""\
群名：{group_name}
发送者：{sender_name}
最后一条消息：{last_message}
近期上下文：
{recent_context}"""

            messages: list[dict[str, str]] = [
                {"role": "system", "content": GATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            logger.info(
                "门控请求 group=%r sender=%r msg=%r",
                group_name,
                sender_name,
                last_message[:50],
            )
            logger.debug("门控 OpenAI 请求体 messages=%s", messages)

            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                stream=False,
            )

            answer = (response.choices[0].message.content or "").strip().upper()
            should = "YES" in answer
            logger.info("门控结果 answer=%r should=%s", answer, should)
            logger.debug("门控 OpenAI 返回体 raw=%s", response)
            return should

        except Exception:
            logger.exception("门控调用失败，默认放行")
            return True
