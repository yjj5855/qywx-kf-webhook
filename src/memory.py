"""多轮对话记忆（服务端存储，按 session 保留最近 N 轮）。

背景：Dify 官方 API 不支持直接改写 Chatflow 历史会话，因此本项目自持一份
"用户消息 + 机器人最终回复" 的记忆（SQLite），在下次回调时格式化为
recentContext 注入主工作流，由主工作流拼进意图分类（聊天记录）的 query，
让多轮意图判断能看到真实的对话内容。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    sender_name  TEXT NOT NULL DEFAULT '',
    user_message TEXT NOT NULL DEFAULT '',
    reply_text   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_session ON chat_memory(session_id, id);
"""

MAX_TURNS = 20     # 每会话最多保留的对话轮数（超出删除最旧）
CTX_TURNS = 6      # 注入意图分类时最多携带的轮数
CTX_MAX_CHARS = 1500  # 注入上下文的文本长度上限（超出裁掉最旧部分）


class ChatMemoryStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)
            conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """兼容旧库：补齐后加的列。"""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_memory)").fetchall()}
        if "sender_name" not in cols:
            conn.execute(
                "ALTER TABLE chat_memory ADD COLUMN sender_name TEXT NOT NULL DEFAULT ''"
            )

    def append(
        self,
        session_id: str,
        user_message: str,
        reply_text: str,
        sender_name: str = "",
    ) -> None:
        """记录一轮对话。reply_text 为空则不记录（如门控跳过）。"""
        if not session_id or not reply_text:
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO chat_memory (session_id, sender_name, user_message, reply_text, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, sender_name, user_message, reply_text, now),
            )
            # 只保留最近 MAX_TURNS 轮
            conn.execute(
                """DELETE FROM chat_memory WHERE session_id = ? AND id NOT IN (
                       SELECT id FROM chat_memory WHERE session_id = ? ORDER BY id DESC LIMIT ?)""",
                (session_id, session_id, MAX_TURNS),
            )
            conn.commit()

    def history(self, session_id: str, limit: int = CTX_TURNS) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT user_message, reply_text, created_at, sender_name FROM chat_memory "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {
                "user_message": r[0],
                "reply_text": r[1],
                "created_at": r[2],
                "sender_name": r[3],
            }
            for r in reversed(rows)
        ]

    def history_since(self, session_id: str, after_id: int = 0, limit: int = 50) -> list[dict]:
        """按 id 增量读取（知识库导出用）：返回 after_id 之后按时间正序的对话。"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, user_message, reply_text, created_at, sender_name FROM chat_memory "
                "WHERE session_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
                (session_id, after_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "user_message": r[1],
                "reply_text": r[2],
                "created_at": r[3],
                "sender_name": r[4],
            }
            for r in rows
        ]

    def to_context(self, session_id: str, limit: int = CTX_TURNS) -> str:
        """把最近几轮对话格式化为注入意图分类 query 的上下文文本。

        格式：
        【历史对话】
        杨佳军: ...
        机器人: ...
        ...
        """
        turns = self.history(session_id, limit)
        if not turns:
            return ""
        lines = ["【历史对话】"]
        for t in turns:
            speaker = t.get("sender_name") or "用户"
            lines.append(f"{speaker}: {t['user_message']}")
            lines.append(f"机器人: {t['reply_text']}")
        text = "\n".join(lines)
        # 长度超限时裁掉最旧部分（保留最近上下文）
        if len(text) > CTX_MAX_CHARS:
            text = "【历史对话】\n" + text[-(CTX_MAX_CHARS - len("【历史对话】\n")):]
        return text


def format_time_cn(iso_str: str) -> str:
    """UTC ISO 时间 → 北京时间字符串（YYYY-MM-DD HH:MM）。解析失败原样返回。"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone(timedelta(hours=8)))  # UTC+8，中国无夏令时
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_str
