"""Dify 工作流应用注册表（workflow_apps 表）。

存「工作流应用 ID → API Key」的映射：group_bindings.workflow_app_id 引用这里的 app_id
（一个群只绑定一个 workflow appid，多个群可共用同一个工作流应用），handler 按群绑定的
app_id 查出该应用的 API Key 后调用 /v1/workflows/run。API Key 存在数据库而非配置文件。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_apps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id     TEXT NOT NULL UNIQUE,          -- Dify 工作流应用 ID（对应 group_bindings.workflow_app_id）
    name       TEXT NOT NULL DEFAULT '',      -- 应用名（如 客服-主流程 / 开户办理-主流程），仅作备注
    api_key    TEXT NOT NULL DEFAULT '',      -- 该应用的 API Key（app-xxx，Dify「API 访问」页生成）
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_COLUMNS = "id, app_id, name, api_key, created_at, updated_at"


class WorkflowAppStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "app_id": row[1],
            "name": row[2],
            "api_key": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def get(self, app_id: str) -> Optional[dict]:
        """按工作流应用 ID 取注册信息（含 api_key）；不存在返回 None。"""
        if not app_id:
            return None
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM workflow_apps WHERE app_id = ?",
                (app_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_api_key(self, app_id: str) -> str:
        """取工作流应用的 API Key；未注册/无 Key 返回空串。"""
        item = self.get(app_id)
        return (item.get("api_key") or "").strip() if item else ""

    def upsert(self, app_id: str, name: str = "", api_key: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"""INSERT INTO workflow_apps (app_id, name, api_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(app_id) DO UPDATE SET
                      name       = excluded.name,
                      api_key    = excluded.api_key,
                      updated_at = excluded.updated_at""",
                (app_id, name, api_key, now, now),
            )
            conn.commit()

    def delete(self, app_id: str) -> bool:
        """删除工作流应用注册；返回是否命中行。"""
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute("DELETE FROM workflow_apps WHERE app_id = ?", (app_id,))
            conn.commit()
        return cur.rowcount > 0

    def list(self) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM workflow_apps ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]
