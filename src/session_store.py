"""按会话维度持久化 Dify 的 conversation_id / qa_conversation_id。

- conversationId：意图识别 Chatflow（聊天记录）的会话，用于多轮"追问补参数"的记忆连续性；
- qaConversationId：客服问答 Chatflow 的会话，用于 QA 多轮上下文。

两个 ID 分属不同 Dify 应用，必须分开存储，不能混用。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_conversations (
    session_id          TEXT PRIMARY KEY,
    conversation_id     TEXT NOT NULL DEFAULT '',
    qa_conversation_id  TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL
);
"""


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def get(self, session_id: str) -> dict:
        """返回 {conversation_id, qa_conversation_id}，无记录时两个字段均为空串。"""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT conversation_id, qa_conversation_id FROM session_conversations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return {"conversation_id": "", "qa_conversation_id": ""}
        return {"conversation_id": row[0] or "", "qa_conversation_id": row[1] or ""}

    def set(self, session_id: str, conversation_id: str = "", qa_conversation_id: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO session_conversations (session_id, conversation_id, qa_conversation_id, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     conversation_id     = excluded.conversation_id,
                     qa_conversation_id  = excluded.qa_conversation_id,
                     updated_at          = excluded.updated_at""",
                (session_id, conversation_id, qa_conversation_id, now),
            )
            conn.commit()
