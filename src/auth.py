"""管理接口鉴权：所有 /api/* 管理接口（群绑定 / workflow 配置 / 对话记忆等）需携带管理密钥。

两种凭据二选一（都校验通过即放行）：
- 请求头：X-API-Key: <WT_ADMIN_API_KEY>
- 请求头：Authorization: Bearer <token>（POST /api/login 用户名密码登录签发，见 api_auth）

- 未配置 WT_ADMIN_API_KEY → 管理接口整体禁用（503，fail-closed），防止裸奔
- 豁免：/callback（WorkTool 回调）、/health、/retrieval（语雀外部知识库，自带 WT_YUQUE_EXTERNAL_KEY 鉴权）、
  /api/login（登录接口本身）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Header, HTTPException

from src.config import settings

ADMIN_KEY_HEADER = "X-API-Key"
BEARER_PREFIX = "Bearer "

# 登录 token 有效期（秒），12 小时
TOKEN_TTL = 12 * 3600


def _signing_key() -> bytes:
    """token 签名密钥：由管理密钥派生，无需额外配置。"""
    return hashlib.sha256(f"qywx-kf-admin::{settings.admin_api_key}".encode()).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(username: str) -> str:
    """签发登录 token：payload {u: 用户名, exp: 过期时间戳} + HMAC-SHA256 签名。"""
    payload = {"u": username, "exp": int(time.time()) + TOKEN_TTL}
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(sig)}"


def verify_token(token: str) -> Optional[str]:
    """校验 token：签名合法且未过期返回用户名，否则 None。"""
    try:
        body, sig_b64 = token.rsplit(".", 1)
        sig = _b64decode(sig_b64)
        expected = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("u") or None
    except Exception:
        return None


def require_admin(
    x_api_key: str = Header(default="", alias=ADMIN_KEY_HEADER),
    authorization: str = Header(default=""),
) -> None:
    """FastAPI 依赖：校验管理接口凭据（X-API-Key 或 Bearer token 二选一）。"""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="管理接口未启用：请在 .env 配置 WT_ADMIN_API_KEY 后重启服务",
        )
    if x_api_key == settings.admin_api_key:
        return
    if authorization.startswith(BEARER_PREFIX):
        token = authorization[len(BEARER_PREFIX):].strip()
        if verify_token(token):
            return
    raise HTTPException(status_code=401, detail="管理接口密钥无效（X-API-Key 或 Bearer token）")


def get_current_user(
    x_api_key: str = Header(default="", alias=ADMIN_KEY_HEADER),
    authorization: str = Header(default=""),
) -> str:
    """FastAPI 依赖：返回当前登录用户名（Bearer token 的 username；X-API-Key 返回配置的管理员名）。"""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="管理接口未启用：请在 .env 配置 WT_ADMIN_API_KEY 后重启服务",
        )
    if x_api_key == settings.admin_api_key:
        return settings.admin_username
    if authorization.startswith(BEARER_PREFIX):
        username = verify_token(authorization[len(BEARER_PREFIX):].strip())
        if username:
            return username
    raise HTTPException(status_code=401, detail="管理接口密钥无效（X-API-Key 或 Bearer token）")
