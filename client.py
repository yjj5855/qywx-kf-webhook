from __future__ import annotations

import httpx

from config import settings
from models import BindCallbackRequest, SendMessageRequest


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
            at_list: @的人列表，@所有人用 [\"@所有人\"]
        """
        item: dict = {
            "type": 203,
            "titleList": [to],
            "receivedContent": content,
        }
        if at_list:
            item["atList"] = at_list
        body = SendMessageRequest(list=[item])
        return await self._post(
            "/wework/sendRawMessage",
            params={"robotId": self.robot_id},
            json=body.model_dump(by_alias=True),
        )

    # ---- 回调配置 ----

    async def bind_callback(self, callback_url: str, callback_type: int = 11) -> dict:
        """绑定回调地址（11=消息回调）"""
        body = BindCallbackRequest(
            callbackUrl=callback_url,
            callbackType=callback_type,
        )
        return await self._post(
            "/robot/robotInfo/callBack/bind",
            params={"robotId": self.robot_id},
            json=body.model_dump(by_alias=True),
        )

    async def get_callback(self) -> dict:
        """查询当前回调配置"""
        return await self._get(
            "/robot/robotInfo/callBack/get",
            params={"robotId": self.robot_id},
        )

    async def unbind_callback(self) -> dict:
        """解绑回调"""
        return await self._post(
            "/robot/robotInfo/callBack/unbind",
            params={"robotId": self.robot_id},
        )

    # ---- 内部方法 ----

    async def _post(self, path: str, **kwargs) -> dict:
        client = await self._get_client()
        resp = await client.post(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def _get(self, path: str, **kwargs) -> dict:
        client = await self._get_client()
        resp = await client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()


# 全局实例（按需初始化）
client: WorkToolClient | None = None


def get_client(robot_id: str) -> WorkToolClient:
    global client
    if client is None or client.robot_id != robot_id:
        client = WorkToolClient(robot_id=robot_id)
    return client
