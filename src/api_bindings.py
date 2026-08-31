"""群绑定管理接口：维护 群 ↔ 公司(company_ids) 绑定关系。

company_ids 由 webhook 侧解析后作为 companyIds 传入主工作流，
供工作流内部路由/公司查询使用。平台目前固定为 wecom（企业微信 WorkTool）。

绑定变更（POST）后会自动尝试把该群的客服档案（docs/公司档案/{group_id}.md）
同步进群知识库；缺档案/未绑定知识库时静默跳过，不影响绑定接口本身。

新增/编辑绑定且未填 memory_dataset_id 时，保存成功后自动调用 Dify API
（POST /v1/datasets，命名 群记忆_{group_id}）创建该群专属知识库并回填绑定；
创建失败不影响绑定保存，仅在响应 warning 中提示。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from src.auth import require_admin
from src.binding import BindingStore, normalize_company_ids
from src.company_profile import sync_group_profile
from src.config import settings
from src.init_datasets import DATASET_NAME_PREFIX, create_dataset
from src.models import BindingItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bindings", tags=["bindings"], dependencies=[Depends(require_admin)])

_store_obj: BindingStore | None = None


def _get_store() -> BindingStore:
    global _store_obj
    if _store_obj is None:
        _store_obj = BindingStore(settings.dify_db_path)
    return _store_obj


@router.get("")
async def list_bindings():
    return {"code": 0, "message": "ok", "data": _get_store().list()}


@router.get("/query")
async def get_binding(platform: str = "wecom", group_id: str = ""):
    if not group_id:
        raise HTTPException(status_code=400, detail="缺少 group_id")
    item = _get_store().get(platform, group_id)
    if item is None:
        raise HTTPException(status_code=404, detail="绑定不存在")
    return {"code": 0, "message": "ok", "data": item}


async def _ensure_dataset(platform: str, group_id: str) -> tuple[str, str]:
    """为该群创建专属知识库并回填绑定；返回 (dataset_id, warning)。

    未配置数据集 Key 或 Dify 调用失败时返回 ("", warning)，不抛异常。
    """
    if not settings.dify_dataset_key:
        return "", "未配置 WT_DIFY_DATASET_KEY，未自动创建知识库（可在绑定中手动填写 memory_dataset_id）"
    name = f"{DATASET_NAME_PREFIX}{group_id}"
    try:
        data = await create_dataset(settings.dify_base_url, settings.dify_dataset_key, name)
        dataset_id = (data or {}).get("id") or ""
        if not dataset_id:
            return "", f"创建知识库「{name}」未返回 id，请到 Dify 后台确认后手动填写 memory_dataset_id"
        _get_store().update_memory_dataset(platform, group_id, dataset_id)
        logger.info("自动创建群知识库并回填 group=%s dataset_id=%s", group_id, dataset_id)
        return dataset_id, ""
    except Exception as exc:
        logger.exception("自动创建群知识库失败 group=%s", group_id)
        return "", f"自动创建知识库失败：{exc}"


@router.post("")
async def upsert_binding(item: BindingItem):
    need_dataset = not (item.memory_dataset_id or "").strip()
    _get_store().upsert(
        platform=item.platform,
        group_id=item.group_id,
        group_name=item.group_name,
        company_ids=normalize_company_ids(item.company_ids),  # 任意分隔符归一化为顿号
        workflow_app_id=item.workflow_app_id,
        open_account_id=item.open_account_id,
        memory_dataset_id=item.memory_dataset_id,
    )
    # 未填知识库 ID：保存成功后自动调用 Dify 创建该群专属知识库并回填
    warning = ""
    if need_dataset:
        dataset_id, warning = await _ensure_dataset(item.platform, item.group_id)
        if dataset_id:
            item.memory_dataset_id = dataset_id
    # 绑定变更后尽量同步最新档案到群知识库；sync_group_profile 内部已兜底异常，
    # 这里仅防 create_task 本身失败（如事件循环未运行），不影响接口响应
    try:
        asyncio.create_task(sync_group_profile(item.platform, item.group_id))
    except Exception:
        logger.exception("触发群公司档案同步失败 group=%s", item.group_id)
    resp: dict = {"code": 0, "message": "ok", "data": _get_store().get(item.platform, item.group_id)}
    if warning:
        resp["warning"] = warning
    return resp


@router.delete("")
async def delete_binding(platform: str = "wecom", group_id: str = ""):
    if not group_id:
        raise HTTPException(status_code=400, detail="缺少 group_id")
    _get_store().delete(platform, group_id)
    return {"code": 0, "message": "ok"}
