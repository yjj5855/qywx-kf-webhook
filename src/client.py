"""WorkTool API 客户端（仅保留当前链路用到的：发送文本消息）。

其余指令（加好友/建群/拉人等）已迁移到 Dify「客服操作工作流」内部执行，
回调绑定等运维接口如需要可再补回。
"""
from __future__ import annotations

import httpx

from src.config import settings


class WorkToolClient:
    """WorkTool API 客户端"""

    def __init__(self, robot_id: str, base_url: str = "") -> None:
        self.base_url = base_url or settings.api_base_url
        self.robot_id = robot_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ---- 发送消息 ----

    async def send_text(self, to: str, content: str, at_list: list[str] | None = None) -> dict:
        """发送文本消息给指定用户/群

        Args:
            to: 接收者（好友昵称/群名/群备注）
            content: 文本内容（\\n 换行）
            at_list: @的人列表，@所有人用 ["@所有人"]
        """
        item: dict = {
            "type": 203,
            "titleList": [to],
            "receivedContent": content,
        }
        if at_list:
            item["atList"] = at_list
        return await self._send_raw(robot_id=self.robot_id, item=item)

    # ---- 内部方法 ----

    async def _send_raw(self, robot_id: str, item: dict) -> dict:
        """发送原始指令（不经过 Pydantic 模型，保留所有字段）"""
        body = {"socketType": 2, "list": [item]}
        return await self._post(
            "/wework/sendRawMessage",
            params={"robotId": robot_id},
            json=body,
        )

    async def _post(self, path: str, **kwargs) -> dict:
        client = await self._get_client()
        resp = await client.post(path, **kwargs)
        resp.raise_for_status()
        return resp.json()


# 全局实例（按需初始化）
client: WorkToolClient | None = None


def get_client(robot_id: str) -> WorkToolClient:
    global client
    if client is None or client.robot_id != robot_id:
        client = WorkToolClient(robot_id=robot_id)
    return client
