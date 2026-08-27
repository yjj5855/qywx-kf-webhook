"""Dify 工作流应用配置接口：维护 工作流应用ID ↔ API Key 注册表（workflow_apps 表）。

workflow_apps 是 workflow 配置表：每条记录一个 Dify 工作流应用（如「客服-主流程」、
「开户办理-主流程」），存放其 API Key。group_bindings.workflow_app_id 引用这里的
app_id，handler 按群绑定的 app_id 查出 Key 后调用 /v1/workflows/run。
API Key 存在数据库而非配置文件。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.workflow_apps import WorkflowAppStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

_store_obj: WorkflowAppStore | None = None


def _get_store() -> WorkflowAppStore:
    global _store_obj
    if _store_obj is None:
        _store_obj = WorkflowAppStore(settings.dify_db_path)
    return _store_obj


class WorkflowAppItem(BaseModel):
    app_id: str                # Dify 工作流应用 ID（对应群绑定 workflow_app_id）
    name: str = ""             # 应用名（如 客服-主流程 / 开户办理-主流程），仅作备注
    api_key: str = ""          # 该应用的 API Key（app-xxx，Dify「API 访问」页生成）


@router.get("")
async def list_workflow_apps():
    return {"code": 0, "message": "ok", "data": _get_store().list()}


@router.post("")
async def upsert_workflow_app(item: WorkflowAppItem):
    app_id = (item.app_id or "").strip()
    if not app_id:
        raise HTTPException(status_code=400, detail="缺少 app_id")
    _get_store().upsert(app_id=app_id, name=item.name, api_key=item.api_key)
    return {"code": 0, "message": "ok", "data": _get_store().get(app_id)}


@router.delete("")
async def delete_workflow_app(app_id: str = ""):
    if not app_id:
        raise HTTPException(status_code=400, detail="缺少 app_id")
    if not _get_store().delete(app_id):
        raise HTTPException(status_code=404, detail="应用未注册")
    return {"code": 0, "message": "ok"}
