"""多轮对话记忆（服务端存储，消息流水模型）。

背景：Dify 官方 API 不支持直接改写 Chatflow 历史会话，因此本项目自持一份
真实对话记忆（SQLite），在下次回调时格式化为 recentContext 注入主工作流，
由主工作流拼进意图分类（聊天记录）的 query，让多轮意图判断能看到真实对话。

存储模型（消息流水，适配多人群聊）：
- 一行 = 一条消息：role（user/bot）+ sender_name + content + created_at；
- 每条群消息都记录（含未@闲聊），机器人回复单独记一条 bot 行；
- 不再强制"一问一答"问答对：多人穿插说话时按时间顺序完整保留。

裁剪策略（避免知识库丢记录）：
- append 只写入、不裁剪；
- 导出成功并推进游标后（exporter），才删除"已导出（id<=游标）且超出
  MAX_TURNS 条"的旧行；未导出的行永远不会被删，保证知识库零丢失。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS chat_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'user',
    sender_name  TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    group_name   TEXT NOT NULL DEFAULT ''
);
"""
_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_memory_session ON chat_memory(session_id, id);"
_SCHEMA = _CREATE_TABLE + _CREATE_INDEX

MAX_TURNS = 40     # 每会话导出后最多保留的消息条数（≈20 轮对话）
CTX_TURNS = 12     # 注入意图分类时最多携带的消息条数（≈6 轮对话）
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
        """兼容旧库：旧"问答对"结构（user_message/reply_text）→ 消息流水结构（role/content）。

        旧行拆分为两条消息：user_message → user 行，reply_text → bot 行。
        注意：迁移后 chat_memory 的 id 会重新分配，group_bindings.kb_last_export_id
        若指向旧 id 需置 0 重新导出（当前各群游标均为 0，无影响）。
        """
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_memory)").fetchall()}
        if "sender_name" not in cols:
            conn.execute(
                "ALTER TABLE chat_memory ADD COLUMN sender_name TEXT NOT NULL DEFAULT ''"
            )
        if "group_name" not in cols:
            conn.execute(
                "ALTER TABLE chat_memory ADD COLUMN group_name TEXT NOT NULL DEFAULT ''"
            )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_memory)").fetchall()}
        if "role" in cols:
            return  # 已是消息流水结构

        conn.execute("ALTER TABLE chat_memory RENAME TO chat_memory_legacy")
        conn.execute(_CREATE_TABLE)
        # 逐行拆分：每行旧问答对 → user 行 + bot 行（保持原始交错顺序，先问后答）
        legacy_rows = conn.execute(
            "SELECT session_id, sender_name, user_message, reply_text, created_at, group_name "
            "FROM chat_memory_legacy ORDER BY id"
        ).fetchall()
        for session_id, sender_name, user_message, reply_text, created_at, group_name in legacy_rows:
            if user_message:
                conn.execute(
                    "INSERT INTO chat_memory (session_id, role, sender_name, content, created_at, group_name)"
                    " VALUES (?, 'user', ?, ?, ?, ?)",
                    (session_id, sender_name, user_message, created_at, group_name),
                )
            if reply_text:
                conn.execute(
                    "INSERT INTO chat_memory (session_id, role, sender_name, content, created_at, group_name)"
                    " VALUES (?, 'bot', '机器人', ?, ?, ?)",
                    (session_id, reply_text, created_at, group_name),
                )
        conn.execute("DROP TABLE chat_memory_legacy")
        conn.execute(_CREATE_INDEX)

    def append(
        self,
        session_id: str,
        content: str,
        sender_name: str = "",
        role: str = "user",
        group_name: str = "",
    ) -> None:
        """记录一条消息（用户消息或机器人回复各一行）。

        role 取值 user / bot；content 为空不记录。
        group_name 用于知识库导出按群匹配（群聊回调同时携带群名与群备注，
        避免 session_id 键不一致导致导不出）；单聊/手动录入可为空。
        注意：这里不做裁剪，裁剪由 exporter 导出成功后执行（见 trim_exported）。
        """
        if not session_id or not content:
            return
        if role not in ("user", "bot"):
            role = "user"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO chat_memory (session_id, role, sender_name, content, created_at, group_name)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, sender_name, content, now, group_name),
            )
            conn.commit()

    def history(self, session_id: str, limit: int = CTX_TURNS) -> list[dict]:
        """最近 limit 条消息（按时间正序）。"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, role, sender_name, content, created_at FROM chat_memory "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "sender_name": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in reversed(rows)
        ]

    def history_since(self, session_id: str, after_id: int = 0, limit: int = 50) -> list[dict]:
        """按 id 增量读取（知识库导出用）：返回 after_id 之后按时间正序的消息。"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, role, sender_name, content, created_at FROM chat_memory "
                "WHERE session_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
                (session_id, after_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "sender_name": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def history_for_group(self, group_name: str, after_id: int = 0, limit: int = 200) -> list[dict]:
        """按群名增量读取（知识库导出用）。

        同时匹配两个来源，避免 session_id 键不一致导致导不出：
        1. group_name 列（新写入的行，群聊回调即使有群备注也带真实群名）；
        2. session_id 前缀 f"{roomType}:{group_name}"（旧行/手动录入行，group_name 为空）。
        """
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, sender_name, content, created_at "
                "FROM chat_memory "
                "WHERE (group_name = ? OR session_id IN (?, ?)) AND id > ? "
                "ORDER BY id ASC LIMIT ?",
                (group_name, f"1:{group_name}", f"3:{group_name}", after_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "role": r[2],
                "sender_name": r[3],
                "content": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    def trim_exported(self, session_ids: list[str], up_to_id: int) -> None:
        """导出后裁剪：删除"已导出（id<=up_to_id）且超出最近 MAX_TURNS 条"的旧行。

        未导出的行（id>up_to_id）永远不会被删，保证知识库不丢记录；
        仅在导出成功并推进游标后调用。
        """
        if not session_ids:
            return
        with sqlite3.connect(self._db_path) as conn:
            for sid in session_ids:
                conn.execute(
                    """DELETE FROM chat_memory WHERE session_id = ? AND id <= ? AND id NOT IN (
                           SELECT id FROM chat_memory WHERE session_id = ? ORDER BY id DESC LIMIT ?)""",
                    (sid, int(up_to_id), sid, MAX_TURNS),
                )
            conn.commit()

    def to_context(self, session_id: str, limit: int = CTX_TURNS) -> str:
        """把最近几条消息格式化为注入意图分类 query 的上下文文本（消息流水，多人原序）。

        格式：
        【历史对话】
        杨佳军: ...
        张三: ...
        机器人: ...
        ...
        """
        msgs = self.history(session_id, limit)
        if not msgs:
            return ""
        lines = ["【历史对话】"]
        for m in msgs:
            if m.get("role") == "bot":
                speaker = "机器人"
            else:
                speaker = m.get("sender_name") or "用户"
            lines.append(f"{speaker}: {m['content']}")
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
