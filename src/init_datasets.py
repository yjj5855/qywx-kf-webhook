"""为每个客服群创建专属 Dify 知识库（数据集），并回填 group_bindings.memory_dataset_id。

用法（仓库根目录）：
    python -m src.init_datasets

前提：
- .env 已配置 WT_DIFY_BASE_URL 与 WT_DIFY_DATASET_KEY（数据集权限类型 Key）
- Dify 已配置 embedding 模型（设置 → 模型供应商 → Embedding），否则 high_quality 索引无法创建

行为：
- 遍历 group_bindings 中 status=1 且 memory_dataset_id 为空的群
- 逐个调用 POST /v1/datasets 创建空知识库（名称：群记忆_{group_id}，索引方式见
  WT_DIFY_DATASET_INDEXING，默认 economy 免向量模型；high_quality 需 Dify 配置 Embedding 模型）
- 创建成功即回填 memory_dataset_id；幂等，可重复执行（已绑定的跳过）
- 文档无需预先上传，运行时由 exporter 定时任务通过 create_by_text 写入
"""
from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from src.binding import BindingStore
from src.config import settings

logger = logging.getLogger(__name__)

DATASET_NAME_PREFIX = "群记忆_"


async def create_dataset(base_url: str, api_key: str, name: str, timeout: float = 30.0) -> dict:
    url = f"{base_url.rstrip('/')}/v1/datasets"
    payload = {
        "name": name,
        "indexing_technique": settings.dify_dataset_indexing,  # economy 或 high_quality（需 Embedding 模型）
        "permission": "all_team_members",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=settings.httpx_trust_env) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        # 把 Dify 返回的错误体带进异常，方便定位 4xx/5xx 根因
        body = exc.response.text[:500]
        raise RuntimeError(f"Dify 创建数据集失败 HTTP {exc.response.status_code} body={body}") from exc


async def create_missing_datasets(only_with_company_ids: bool = False) -> dict:
    """为未绑定知识库的群创建数据集。

    only_with_company_ids=True 时只处理已填 company_ids 的群（优先保证有业务的公司群）。
    """
    store = BindingStore(settings.dify_db_path)
    bindings = []
    for b in store.list():
        if (b.get("memory_dataset_id") or "").strip():
            continue  # 已绑定知识库，跳过
        if only_with_company_ids and not (b.get("company_ids") or "").strip():
            continue  # 只创建有公司ID的群
        bindings.append(b)
    created = failed = 0

    for b in bindings:
        group_id = (b.get("group_id") or "").strip()
        if not group_id:
            continue
        name = f"{DATASET_NAME_PREFIX}{group_id}"
        try:
            data = await create_dataset(settings.dify_base_url, settings.dify_dataset_key, name)
            dataset_id = (data or {}).get("id") or ""
            if not dataset_id:
                logger.warning("创建数据集未返回 id name=%s resp=%s", name, data)
                failed += 1
                continue
            store.update_memory_dataset(b.get("platform", "wecom"), group_id, dataset_id)
            created += 1
            logger.info("已创建并绑定知识库 group=%s dataset_id=%s", group_id, dataset_id)
        except Exception:
            logger.exception("创建知识库失败 group=%s", group_id)
            failed += 1

    return {"created": created, "failed": failed, "skipped": len(bindings) - created - failed, "total": len(bindings)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not settings.dify_dataset_key:
        print("未配置 WT_DIFY_DATASET_KEY，请先在 .env 配置【数据集权限】类型的 Key")
        sys.exit(1)
    only_with_company = "--with-company" in sys.argv
    scope = "已填公司ID的群" if only_with_company else "全部未绑定知识库的群"
    print(f"开始为 {settings.dify_db_path} 中{scope}创建数据集...")
    result = asyncio.run(create_missing_datasets(only_with_company_ids=only_with_company))
    print("完成：", result)


if __name__ == "__main__":
    main()
