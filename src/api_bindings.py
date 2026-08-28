"""群绑定管理接口：维护 群 ↔ 公司(company_ids) 绑定关系。

company_ids 由 webhook 侧解析后作为 companyIds 传入主工作流，
供工作流内部路由/公司查询使用。平台目前固定为 wecom（企业微信 WorkTool）。

绑定变更（POST）后会自动尝试把该群的客服档案（docs/公司档案/{group_id}.md）
同步进群知识库；缺档案/未绑定知识库时静默跳过，不影响绑定接口本身。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from src.auth import require_admin
from src.binding import BindingStore, normalize_company_ids
from src.company_profile import sync_group_profile
from src.config import settings
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


@router.post("")
async def upsert_binding(item: BindingItem):
    _get_store().upsert(
        platform=item.platform,
        group_id=item.group_id,
        group_name=item.group_name,
        company_ids=normalize_company_ids(item.company_ids),  # 任意分隔符归一化为顿号
        workflow_app_id=item.workflow_app_id,
        memory_dataset_id=item.memory_dataset_id,
    )
    # 绑定变更后尽量同步最新档案到群知识库；sync_group_profile 内部已兜底异常，
    # 这里仅防 create_task 本身失败（如事件循环未运行），不影响接口响应
    try:
        asyncio.create_task(sync_group_profile(item.platform, item.group_id))
    except Exception:
        logger.exception("触发群公司档案同步失败 group=%s", item.group_id)
    return {"code": 0, "message": "ok", "data": _get_store().get(item.platform, item.group_id)}


@router.delete("")
async def delete_binding(platform: str = "wecom", group_id: str = ""):
    if not group_id:
        raise HTTPException(status_code=400, detail="缺少 group_id")
    _get_store().delete(platform, group_id)
    return {"code": 0, "message": "ok"}
