"""群与公司/工作流绑定关系存储（执行文档 cs_group_workflow_binding 的轻量实现）。

company_ids 以顿号（、）分隔字符串存储（兼容逗号/分号，避免与 CSV 列分隔符冲突），
读取时在 Python 侧按 [,、;] 切分成列表，不使用 SQL LIKE 模糊匹配。
memory_dataset_id 为该群的专属 Dify 知识库 ID（群聊天记录导出用）。
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS group_bindings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    platform          TEXT NOT NULL,
    group_id          TEXT NOT NULL,
    group_name        TEXT NOT NULL DEFAULT '',
    company_ids       TEXT NOT NULL DEFAULT '',
    workflow_app_id   TEXT NOT NULL DEFAULT '',
    memory_dataset_id TEXT NOT NULL DEFAULT '',
    kb_last_export_id INTEGER NOT NULL DEFAULT 0,
    status            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(platform, group_id)
);
"""

_COLUMNS = (
    "id, platform, group_id, group_name, company_ids, "
    "workflow_app_id, memory_dataset_id, kb_last_export_id, status, created_at, updated_at"
)


def normalize_company_ids(raw: str) -> str:
    """公司ID归一化：任意分隔符（/、,;、，；、空格、竖线）→ 顿号、分隔，并去除空白。

    CSV 回填时多用 / 分隔；统一入库为顿号，读取时按 [、,;] 兼容切分。
    """
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"[、,;，；/／|\s]+", raw) if p.strip()]
    return "、".join(parts)


class BindingStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(_SCHEMA)
            self._migrate(conn)
            conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """兼容旧库：补齐后加的列。"""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(group_bindings)").fetchall()}
        if "memory_dataset_id" not in cols:
            conn.execute(
                "ALTER TABLE group_bindings ADD COLUMN memory_dataset_id TEXT NOT NULL DEFAULT ''"
            )
        if "kb_last_export_id" not in cols:
            conn.execute(
                "ALTER TABLE group_bindings ADD COLUMN kb_last_export_id INTEGER NOT NULL DEFAULT 0"
            )

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "platform": row[1],
            "group_id": row[2],
            "group_name": row[3],
            "company_ids": row[4],
            "workflow_app_id": row[5],
            "memory_dataset_id": row[6],
            "kb_last_export_id": row[7],
            "status": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def get(self, platform: str, group_id: str) -> Optional[dict]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM group_bindings "
                "WHERE platform = ? AND group_id = ? AND status = 1",
                (platform, group_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_any(self, platform: str, group_id: str) -> Optional[dict]:
        """不限状态取绑定（初始化脚本保留字段用，停用行也返回）。"""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM group_bindings "
                "WHERE platform = ? AND group_id = ?",
                (platform, group_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_group_name(self, platform: str, group_name: str) -> Optional[dict]:
        """按群名反查绑定（WorkTool 回调只有群名时使用）。

        群名唯一 → 返回该绑定；无匹配或重名（多行同名）→ 返回 None 并记日志。
        """
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM group_bindings "
                "WHERE platform = ? AND group_name = ? AND status = 1",
                (platform, group_name),
            ).fetchall()
        if len(rows) == 1:
            return self._row_to_dict(rows[0])
        if len(rows) > 1:
            logger.warning("群名重名，无法确定唯一绑定 platform=%s group_name=%r", platform, group_name)
        return None

    def exists(self, platform: str, group_id: str) -> bool:
        """是否存在该绑定（不限状态，初始化脚本判断 insert/update 用）。"""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM group_bindings WHERE platform = ? AND group_id = ?",
                (platform, group_id),
            ).fetchone()
        return row is not None

    def upsert(
        self,
        platform: str,
        group_id: str,
        group_name: str = "",
        company_ids: str = "",
        workflow_app_id: str = "",
        memory_dataset_id: str = "",
        status: int = 1,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"""INSERT INTO group_bindings
                       (platform, group_id, group_name, company_ids, workflow_app_id,
                        memory_dataset_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(platform, group_id) DO UPDATE SET
                     group_name        = excluded.group_name,
                     company_ids       = excluded.company_ids,
                     workflow_app_id   = excluded.workflow_app_id,
                     memory_dataset_id = excluded.memory_dataset_id,
                     status            = excluded.status,
                     updated_at        = excluded.updated_at""",
                (platform, group_id, group_name, company_ids, workflow_app_id,
                 memory_dataset_id, status, now, now),
            )
            conn.commit()

    def delete(self, platform: str, group_id: str) -> None:
        """软删除：status 置 0。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE group_bindings SET status = 0, updated_at = ? WHERE platform = ? AND group_id = ?",
                (now, platform, group_id),
            )
            conn.commit()

    def update_export_cursor(self, platform: str, group_id: str, last_id: int) -> None:
        """记录知识库增量导出游标（chat_memory 的最大已导出 id）。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE group_bindings SET kb_last_export_id = ? WHERE platform = ? AND group_id = ?",
                (int(last_id), platform, group_id),
            )
            conn.commit()

    def update_company_ids(self, platform: str, group_id: str, company_ids: str) -> bool:
        """仅更新公司ID列，不触碰 group_name / status / 知识库 / 工作流等其他字段。

        供最小更新文件（仅 群ID、公司ID 两列）使用，返回是否命中行。
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE group_bindings SET company_ids = ?, updated_at = ? "
                "WHERE platform = ? AND group_id = ?",
                (company_ids, now, platform, group_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def update_memory_dataset(self, platform: str, group_id: str, dataset_id: str) -> None:
        """回填群专属知识库 ID。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE group_bindings SET memory_dataset_id = ? WHERE platform = ? AND group_id = ?",
                (dataset_id, platform, group_id),
            )
            conn.commit()

    def update_workflow_app(self, platform: str, group_id: str, workflow_app_id: str) -> bool:
        """回填群绑定的 Dify 工作流应用 ID（workflow_app_id 列，引用 workflow 配置表）。

        一个群只绑定一个 workflow appid：handler 按此 app_id 从 workflow_apps 表查 API Key
        后调用对应工作流应用（如「开户办理-主流程」）；空值/未注册则不调用工作流。返回是否命中行。
        """
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE group_bindings SET workflow_app_id = ? WHERE platform = ? AND group_id = ?",
                (workflow_app_id, platform, group_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_legacy_name_keyed(self, names: list[str]) -> None:
        """清理旧版按群名做主键的历史绑定（group_id==group_name 且群名已被 G 编码取代）。

        避免初始化 G 编码后，按群名反查时命中旧行造成重名冲突。
        """
        names = [n for n in names if n]
        if not names:
            return
        placeholders = ",".join("?" * len(names))
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"DELETE FROM group_bindings WHERE status = 1 AND group_id = group_name "
                f"AND group_id IN ({placeholders})",
                names,
            )
            conn.commit()

    def list(self) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM group_bindings WHERE status = 1 ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_company_ids(self, platform: str, group_id: str) -> list[str]:
        """取群绑定公司的 ID 列表；未绑定或已停用返回空列表。

        分隔符兼容顿号/逗号/分号（[、,;]），旧数据不受影响。
        """
        item = self.get(platform, group_id)
        if not item:
            return []
        return [c.strip() for c in re.split(r"[、,;]", item["company_ids"] or "") if c.strip()]
