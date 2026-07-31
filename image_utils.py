from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static" / "images"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# 支持的图片格式 magic bytes
_MIME_MAP: dict[bytes, str] = {
    b"\x89PNG": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF8": "gif",
    b"RIFF": "webp",  # WebP 使用 RIFF 容器
}


def _detect_ext(data: bytes) -> str:
    """根据文件头检测图片格式"""
    for magic, ext in _MIME_MAP.items():
        if data.startswith(magic):
            return ext
    return "png"  # 默认


def save_base64_image(b64_string: str) -> str | None:
    """将 base64 图片保存到 static/images/ 目录。

    Returns:
        保存成功返回相对于 static 目录的路径（如 images/abc.png），失败返回 None。
    """
    if not b64_string:
        return None
    try:
        data = base64.b64decode(b64_string)
        ext = _detect_ext(data)
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = STATIC_DIR / filename
        filepath.write_bytes(data)
        logger.info("图片已保存 path=%s size=%d", filepath, len(data))
        return f"images/{filename}"
    except Exception:
        logger.exception("图片保存失败")
        return None
