"""群绑定管理接口：维护 群 ↔ 公司(company_ids) 绑定关系。

公司信息查询（action=company_info_query）依赖这里查到的 company_ids 去调公司接口。
平台目前固定为 wecom（企业微信 WorkTool）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.binding import BindingStore, normalize_company_ids
from src.config import settings
from src.models import BindingItem

router = APIRouter(prefix="/bindings", tags=["bindings"])

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
    return {"code": 0, "message": "ok", "data": _get_store().get(item.platform, item.group_id)}


@router.delete("")
async def delete_binding(platform: str = "wecom", group_id: str = ""):
    if not group_id:
        raise HTTPException(status_code=400, detail="缺少 group_id")
    _get_store().delete(platform, group_id)
    return {"code": 0, "message": "ok"}
