"""管理后台登录接口：用户名/密码 → Bearer token。

登录成功后前端把 token 放 Authorization: Bearer <token> 头访问 /api/* 管理接口；
token 由 src.auth.create_token 签发（HMAC 签名，12 小时过期），与 X-API-Key 等效。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth import TOKEN_TTL, create_token, get_current_user
from src.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


@router.post("/login")
async def login(req: LoginRequest):
    """用户名/密码登录，成功返回 Bearer token（12 小时有效）。"""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="管理接口未启用：请在 .env 配置 WT_ADMIN_API_KEY 后重启服务",
        )
    if not settings.admin_password:
        raise HTTPException(
            status_code=503,
            detail="未配置 WT_ADMIN_PASSWORD，登录接口已禁用（请改用 X-API-Key）",
        )
    username = (req.username or "").strip()
    if username == settings.admin_username and req.password == settings.admin_password:
        token = create_token(username)
        return {
            "code": 0,
            "message": "ok",
            "data": {"token": token, "username": username, "expires_in": TOKEN_TTL},
        }
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.get("/me")
async def me(username: str = Depends(get_current_user)):
    """返回当前登录用户名（前端页面刷新时校验 token 是否有效用）。"""
    return {"code": 0, "message": "ok", "data": {"username": username}}
