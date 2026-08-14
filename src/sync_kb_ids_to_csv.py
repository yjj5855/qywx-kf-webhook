"""把 group_bindings.memory_dataset_id 回填到客户群 CSV（新增/更新「知识库ID」列）。

用法（仓库根目录）：
    python -m src.sync_kb_ids_to_csv [csv路径]

- 按「群ID」匹配数据库绑定，写入 memory_dataset_id；未匹配/为空则写空串
- 保留 CSV 原有全部列（含 BOM，Excel 可直接打开），知识库ID 列追加在最后
- 幂等，可重复执行（新创建知识库后重新跑即可刷新）
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

from src.config import settings

CSV_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "客户群列表_去重_公司ID回填.csv"
KB_COL = "知识库ID"
WF_COL = "工作流AppID"


def sync_to_csv(csv_path: str | Path) -> dict:
    with sqlite3.connect(settings.dify_db_path) as conn:
        rows = conn.execute(
            "SELECT group_id, memory_dataset_id, workflow_app_id FROM group_bindings"
        ).fetchall()
    id2ds = {gid: (ds or "") for gid, ds, _wf in rows}
    id2wf = {gid: (wf or "") for gid, _ds, wf in rows}

    with open(csv_path, encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        fieldnames = list(reader.fieldnames or [])
        data = list(reader)

    for col in (KB_COL, WF_COL):
        if col not in fieldnames:
            fieldnames.append(col)

    filled_kb = filled_wf = 0
    for row in data:
        group_id = (row.get("群ID") or "").strip()
        ds = id2ds.get(group_id, "")
        row[KB_COL] = ds
        if ds:
            filled_kb += 1
        wf = id2wf.get(group_id, "")
        row[WF_COL] = wf
        if wf:
            filled_wf += 1

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    return {"rows": len(data), "with_kb_id": filled_kb, "with_wf_id": filled_wf}


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else str(CSV_DEFAULT)
    print(f"回填 CSV <- 数据库 {settings.dify_db_path} -> {csv_path}")
    result = sync_to_csv(csv_path)
    print("完成：", result)


if __name__ == "__main__":
    main()
