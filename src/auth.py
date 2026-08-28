"""管理接口鉴权：所有 /api/* 管理接口（群绑定 / workflow 配置 / 对话记忆等）需携带管理密钥。

- 请求头：X-API-Key: <WT_ADMIN_API_KEY>
- 未配置 WT_ADMIN_API_KEY → 管理接口整体禁用（503，fail-closed），防止裸奔
- 豁免：/callback（WorkTool 回调）、/health、/retrieval（语雀外部知识库，自带 WT_YUQUE_EXTERNAL_KEY 鉴权）
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from src.config import settings

ADMIN_KEY_HEADER = "X-API-Key"


def require_admin(x_api_key: str = Header(default="", alias=ADMIN_KEY_HEADER)) -> None:
    """FastAPI 依赖：校验管理接口密钥。"""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="管理接口未启用：请在 .env 配置 WT_ADMIN_API_KEY 后重启服务",
        )
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="管理接口密钥无效（X-API-Key）")
