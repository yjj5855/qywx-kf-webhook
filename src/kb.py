"""群聊天记录 → 知识库文件。

数据源：本项目 SQLite 中的真实对话记忆（src/memory.py），而不是 Dify Chatflow
的会话历史（那里存的是意图 JSON，不适合做知识库）。

流程：读取某群最近对话（支持 since_id 增量）→ 格式化文本 →
调用 Dify 数据集 API（POST /v1/datasets/{dataset_id}/document/create_by_text）
写入群专属知识库。如需先做 LLM 总结再入库，可在 build_dialogue_text 之前加一步。
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def build_dialogue_text(turns: list[dict]) -> str:
    """把若干轮对话格式化为知识库文档文本，每行附带北京时间（YYYY-MM-DD HH:MM）。"""
    from src.memory import format_time_cn

    lines = []
    for t in turns:
        ts = format_time_cn(t.get("created_at") or "")
        suffix = f"（{ts}）" if ts else ""
        if t.get("user_message"):
            speaker = t.get("sender_name") or "用户"
            lines.append(f"{speaker}: {t['user_message']}{suffix}")
        if t.get("reply_text"):
            lines.append(f"机器人: {t['reply_text']}{suffix}")
    return "\n".join(lines)


async def create_dataset_document(
    base_url: str,
    api_key: str,
    dataset_id: str,
    name: str,
    text: str,
    timeout: float = 30.0,
) -> dict:
    """调用 Dify 创建知识库文档（create_by_text），返回响应 JSON。

    注意：api_key 必须是「数据集」权限类型的 Dify API Key（应用「API 访问」页创建）。
    """
    url = f"{base_url.rstrip('/')}/v1/datasets/{dataset_id}/document/create_by_text"
    payload = {"name": name, "text": text}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def export_turns(
    base_url: str,
    api_key: str,
    dataset_id: str,
    name_prefix: str,
    turns: list[dict],
    seq: int = 0,
) -> dict:
    """把若干轮对话写入知识库文档（格式化 + 建文档），返回 create_by_text 响应。

    手动导出（/api/messages/export）与定时任务（exporter.kb_export_loop）共用。
    """
    text = build_dialogue_text(turns)
    if not text.strip():
        raise ValueError("没有可导出的对话内容")
    name = name_prefix + (f"_{seq}" if seq else "")
    return await create_dataset_document(base_url, api_key, dataset_id, name, text)
