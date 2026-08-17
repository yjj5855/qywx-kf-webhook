"""公司信息查询（应用层执行）。

主工作流识别出 COMPANY_INFO_QUERY 后，结束节点输出 action=company_info_query
（query_type/keyword/period/params），本模块负责用"群绑定的 company_ids"
调用公司接口并生成可直接回复给用户的文本。

默认实现 HttpCompanyInfoProvider 的接口契约（如你的公司接口结构不同，改这里即可）：
    POST {COMPANY_API_BASE_URL}/v1/company/query
    body: {"company_ids": ["1001"], "query_type": "employee_info",
           "keyword": "张三", "period": "2025年3月"}
    期望返回: {"code": 0, "message": "ok", "data": {..., "text": "查询结果文本"}}
    data 兼容三种形态：
      - data.text 字符串 → 直接作为回复
      - data 为字符串 → 直接作为回复
      - data 为其它 JSON → 自动序列化为文本
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class CompanyInfoProvider(ABC):
    @abstractmethod
    async def query(
        self,
        *,
        company_ids: list[str],
        query_type: str,
        keyword: str,
        period: str,
    ) -> str:
        """返回可直接发给用户的回复文本。"""


class HttpCompanyInfoProvider(CompanyInfoProvider):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 15.0) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def query(
        self,
        *,
        company_ids: list[str],
        query_type: str,
        keyword: str,
        period: str,
    ) -> str:
        url = f"{self._base_url}/v1/company/query"
        payload = {
            "company_ids": company_ids,
            "query_type": query_type or "",
            "keyword": keyword or "",
            "period": period or "",
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        code = data.get("code")
        if code is not None and str(code) != "0":
            return f"查询失败：{data.get('message') or data.get('msg') or '未知错误'}"

        d = data.get("data")
        if isinstance(d, str):
            return d if d else "查询完成，但未返回可展示的数据。"
        if isinstance(d, dict):
            if d.get("text"):
                return str(d["text"])
            return json.dumps(d, ensure_ascii=False)
        return "查询完成，但未返回可展示的数据。"


class FallbackCompanyInfoProvider(CompanyInfoProvider):
    """未配置公司接口时的兜底：给出明确提示，避免用户误以为没查到。"""

    async def query(
        self,
        *,
        company_ids: list[str],
        query_type: str,
        keyword: str,
        period: str,
    ) -> str:
        return "公司信息查询接口尚未配置，请联系管理员设置 WT_COMPANY_API_BASE_URL 后重试。"


def build_company_provider() -> CompanyInfoProvider:
    if settings.company_api_base_url:
        return HttpCompanyInfoProvider(settings.company_api_base_url, settings.company_api_key)
    return FallbackCompanyInfoProvider()
