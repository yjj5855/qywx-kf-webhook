"""语雀外部知识库胶水服务：Dify 外部知识库检索适配层。

Dify「知识库 → 连接外部知识库」把检索请求 POST 到本服务的 /retrieval，
本服务负责：鉴权（Dify 配置的 API Key）→ 调用语雀搜索 API → 拉取文档正文
→ 按 Dify 外部知识库 API 规范返回 records。

- Dify 外部知识库 API 规范：https://docs.dify.ai/zh/cloud/use-dify/knowledge/external-knowledge-api
- 语雀开放 API：https://www.yuque.com/yuque/developer/api
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["yuque"])

YUQUE_API_BASE = settings.yuque_api_base.rstrip("/")
# 语雀要求带 User-Agent
_YUQUE_HEADERS = {"User-Agent": "Dify-External-Knowledge/1.0"}


# ---- Dify 外部知识库 API 请求/响应模型 ----

class RetrievalSetting(BaseModel):
    top_k: int = 3
    score_threshold: float = 0.0


class DifyRetrievalRequest(BaseModel):
    knowledge_id: str = ""                       # Dify 连接外部知识库时填写的 ID，如 yuque-wiki
    query: str
    retrieval_setting: RetrievalSetting | None = None
    # Dify 程序化调用会传元数据过滤条件（UI 暂未开放配置），此处预留，不参与过滤
    metadata_condition: dict | None = None


class Record(BaseModel):
    content: str
    score: float
    title: str
    metadata: dict = Field(default_factory=dict)


class DifyRetrievalResponse(BaseModel):
    records: list[Record] = Field(default_factory=list)


# ---- 语雀搜索工具 ----

def _resolve_scope(knowledge_id: str) -> str:
    """按 Dify 传的外部知识库 ID 解析语雀搜索范围。

    优先级：WT_YUQUE_KB_SCOPES 中 knowledge_id 对应的 scope > 默认 WT_YUQUE_SCOPE > 空（搜全部可见）。
    scope 形如 "团队login/知识库slug"，例如 "myteam/mywiki"。
    """
    if knowledge_id:
        try:
            mapping = json.loads(settings.yuque_kb_scopes or "{}")
        except json.JSONDecodeError:
            logger.warning("WT_YUQUE_KB_SCOPES 不是合法 JSON，已忽略")
            mapping = {}
        if mapping.get(knowledge_id):
            return mapping[knowledge_id]
    return settings.yuque_scope


def _extract_doc_ids(hit: dict) -> tuple[int | None, int | None]:
    """从一条搜索结果中兼容提取 (repo_id, doc_id)。

    新版搜索结果形如 {"type": "doc", "target": {..., "book": {...}}}，
    旧版形如 {"id": ..., "repo": {"id": ...}}，两种都兼容。
    """
    target = hit.get("target") or {}
    repo_id = (
        (target.get("book") or {}).get("id")
        or target.get("book_id")
        or (hit.get("repo") or {}).get("id")
    )
    doc_id = target.get("id") or hit.get("id")
    return repo_id, doc_id


async def _fetch_full_content(client: httpx.AsyncClient, hit: dict) -> str:
    """获取文档完整 Markdown 正文：优先用搜索结果自带的 target.body，否则二次调用文档详情接口。"""
    target = hit.get("target") or {}
    body = target.get("body") or ""
    if body:
        return body

    repo_id, doc_id = _extract_doc_ids(hit)
    if repo_id and doc_id:
        try:
            resp = await client.get(f"{YUQUE_API_BASE}/repos/{repo_id}/docs/{doc_id}")
            resp.raise_for_status()
            body = (resp.json().get("data") or {}).get("body") or ""
        except Exception:
            logger.exception("语雀文档详情获取失败 repo_id=%s doc_id=%s", repo_id, doc_id)

    # 拿不到正文时退化为摘要，保证 records 不为空
    return body or hit.get("summary") or target.get("description") or hit.get("description") or ""


def _score_by_rank(idx: int) -> float:
    """按搜索排名粗略估算相似度（第 1 名 0.95，逐名递减 0.1，最低 0.1）。

    语雀搜索不返回相关性分数，这里只保证 Dify 能按分数排序/阈值过滤；
    如需真实语义相似度，可后续接入 embedding/rerank。
    """
    return max(0.1, 0.95 - idx * 0.1)


# ---- Dify 外部知识库检索接口 ----

@router.post("/retrieval")
async def yuque_retrieval(
    request: DifyRetrievalRequest,
    authorization: str | None = Header(None),
):
    """Dify 外部知识库检索端点（POST /retrieval）。

    请求头需带 `Authorization: Bearer {WT_YUQUE_EXTERNAL_KEY}`。
    返回 Dify 规范：`{"records": [{"content", "score", "title", "metadata"}]}`。
    """
    # 1. 鉴权（Dify 配置的 API Key）
    if not settings.yuque_external_key:
        return JSONResponse(status_code=503, content={
            "error_code": 1002,
            "error_msg": "External knowledge service is not configured (WT_YUQUE_EXTERNAL_KEY).",
        })
    sent_key = (authorization or "").replace("Bearer ", "", 1).strip()
    if not sent_key or sent_key != settings.yuque_external_key:
        logger.warning("外部知识库鉴权失败 knowledge_id=%r", request.knowledge_id)
        # 与 Dify 文档错误示例保持一致：错误体是顶层 {error_code, error_msg}
        return JSONResponse(status_code=401, content={
            "error_code": 1002,
            "error_msg": "Authorization failed. Please check your API key.",
        })

    if not settings.yuque_token:
        logger.error("未配置 WT_YUQUE_TOKEN，无法调用语雀 API")
        return JSONResponse(status_code=503, content={
            "error_code": 2001,
            "error_msg": "Yuque token is not configured (WT_YUQUE_TOKEN).",
        })

    rs = request.retrieval_setting or RetrievalSetting()
    top_k = max(1, min(rs.top_k or 3, 20))
    threshold = rs.score_threshold or 0.0
    scope = _resolve_scope(request.knowledge_id)

    # 2. 调用语雀搜索
    headers = {**_YUQUE_HEADERS, "X-Auth-Token": settings.yuque_token}
    search_params = {"q": request.query, "type": "doc", "limit": top_k}
    if scope:
        search_params["scope"] = scope

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), trust_env=False) as client:
            search_resp = await client.get(
                f"{YUQUE_API_BASE}/search",
                params=search_params,
                headers=headers,
            )
            search_resp.raise_for_status()
            hits = (search_resp.json().get("data") or [])[:top_k]
            logger.info(
                "语雀检索 knowledge_id=%r q=%r scope=%r hits=%d",
                request.knowledge_id, request.query, scope or "-", len(hits),
            )

            # 3. 并行拉取正文，组装 records
            contents = await asyncio.gather(
                *(_fetch_full_content(client, hit) for hit in hits)
            )
    except httpx.HTTPError as exc:
        logger.exception("语雀搜索失败 q=%r", request.query)
        return JSONResponse(status_code=502, content={
            "error_code": 2001,
            "error_msg": f"语雀搜索失败: {exc}",
        })

    records = []
    for idx, (hit, content) in enumerate(zip(hits, contents)):
        if not content:
            continue
        score = _score_by_rank(idx)
        if score < threshold:
            continue
        target = hit.get("target") or {}
        repo_id, doc_id = _extract_doc_ids(hit)
        records.append(Record(
            content=content,
            score=score,
            title=target.get("title") or hit.get("title") or "无标题",
            # metadata 必须是对象（不能为 null），否则 Dify 检索流程会报错
            metadata={
                "path": target.get("url") or hit.get("url") or "",
                "repo_id": repo_id,
                "doc_id": doc_id,
                "description": target.get("description")
                or hit.get("summary")
                or hit.get("description")
                or "",
            },
        ))

    return DifyRetrievalResponse(records=records)
