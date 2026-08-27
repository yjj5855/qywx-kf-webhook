"""Dify 工作流调用客户端。

只负责一件事：把整理好的参数以 blocking 模式提交给 Dify 主工作流
（/v1/workflows/run），并返回结束节点输出的字段字典。
"""
from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)


class DifyError(Exception):
    """Dify 调用失败（网络错误、鉴权失败、工作流执行异常等）"""


class DifyWorkflowClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def run_workflow(self, inputs: dict, user: str) -> dict:
        """调用 Dify 工作流（blocking），返回结束节点输出字段字典。

        工作流结束节点输出 final_text（最终发送到群里的文本）；无输出则返回空 dict。
        工作流 API Key 由调用方传入（handler 按群绑定 workflow_app_id 取）。
        """
        if not self._base_url or not self._api_key:
            raise DifyError("未配置 Dify 工作流（WT_DIFY_BASE_URL / 群绑定 workflow_app_id 列）")

        url = f"{self._base_url}/v1/workflows/run"
        payload = {
            "inputs": inputs or {},
            "response_mode": "blocking",
            "user": user,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise DifyError(f"Dify 工作流调用超时（{self._timeout}s）") from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise DifyError(f"Dify 工作流返回 HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise DifyError(f"Dify 工作流调用失败：{exc}") from exc

        if not isinstance(data, dict):
            logger.warning("Dify 工作流返回异常 data=%r", data)
            return {}

        # 兼容两种响应结构：
        # - 新版 Dify：结束节点输出在 data.outputs（顶层无 result 字段）
        # - 旧版 Dify：输出在顶层 result（可能是 dict 或 JSON 字符串）
        result = data.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = None
        if not isinstance(result, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                result = inner.get("outputs")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except (json.JSONDecodeError, TypeError):
                        result = None
        if not isinstance(result, dict):
            logger.warning("Dify 工作流返回异常（无输出字段）data=%r", data)
            return {}
        return result
