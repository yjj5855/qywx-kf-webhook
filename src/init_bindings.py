"""使用 docs/客户群列表_去重.csv 初始化 group_bindings 数据库。

用法（仓库根目录）：
    python -m src.init_bindings [csv路径]     # 默认 docs/客户群列表_去重.csv

CSV 列：群ID, 群名, 公司ID, 群人数, 群主, 群主所在部门, 创建时间, 状态[, 知识库ID, 工作流AppID]
映射规则：
- group_id   = 群ID（G 编码，稳定标识；WorkTool 回调无稳定群ID，靠群名反查）
- group_name = 群名（回调 chat_id 按此反查绑定）
- company_ids= 公司ID（多个用顿号、分隔，可空；回填后重新执行即可更新）
- 状态"正常"→ status=1；"重名冲突…"→ status=0（待企微侧重命名后重新导入）
- 工作流AppID：CSV 该列非空时回填到 workflow_app_id（一个群只绑定一个 workflow appid，
  handler 按此值调用对应 Dify 工作流应用，如「开户办理-主流程」）；CSV 为空时保留库内已有值
- memory_dataset_id / kb_last_export_id 不会被覆盖（保留已有值）
- 清理旧版按群名做主键（group_id==group_name）的历史绑定行，避免按名反查时重名冲突
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

from src.binding import BindingStore, normalize_company_ids
from src.config import settings
from src.memory import ChatMemoryStore

logger = logging.getLogger(__name__)

CSV_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "客户群列表_去重.csv"


def init_from_csv(csv_path: str | Path = CSV_DEFAULT) -> dict:
    # 确保全部表结构存在（group_bindings / chat_memory）
    store = BindingStore(settings.dify_db_path)
    ChatMemoryStore(settings.dify_db_path)
    inserted = updated = normal = conflict = 0
    csv_names: set[str] = set()
    rows: list[dict] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            group_id = (row.get("群ID") or "").strip()
            group_name = (row.get("群名") or "").strip()
            if not group_id:
                continue
            rows.append(row)
            if group_name:
                csv_names.add(group_name)

    # 清理旧版按群名做主键的历史行（group_id == group_name，且群名在 CSV 中已有 G 编码对应）
    store.delete_legacy_name_keyed(list(csv_names))

    for row in rows:
        group_id = (row.get("群ID") or "").strip()
        group_name = (row.get("群名") or "").strip()
        company_ids = (row.get("公司ID") or "").strip()
        is_normal = (row.get("状态") or "").strip() == "正常"
        status = 1 if is_normal else 0

        existed = store.exists("wecom", group_id)
        existing = store.get_any("wecom", group_id)  # 不限状态，保留停用行的字段
        # 工作流AppID：CSV 非空则回填（一个群只绑定一个 workflow appid），空则保留已有值
        csv_workflow = (row.get("工作流AppID") or "").strip()
        workflow_app_id = (
            csv_workflow
            if csv_workflow
            else (existing.get("workflow_app_id", "") if existing else "")
        )
        store.upsert(
            platform="wecom",
            group_id=group_id,
            group_name=group_name,
            # 任意分隔符（CSV 常用 /）统一归一化为顿号
            company_ids=normalize_company_ids(company_ids),
            workflow_app_id=workflow_app_id,
            # 知识库 / 导出游标 不在 CSV 中，保留已有值，避免误清
            memory_dataset_id=existing.get("memory_dataset_id", "") if existing else "",
            status=status,
        )
        if existed:
            updated += 1
        else:
            inserted += 1
        if is_normal:
            normal += 1
        else:
            conflict += 1

    summary = {
        "inserted": inserted,
        "updated": updated,
        "normal": normal,
        "conflict_disabled": conflict,
        "total": len(rows),
    }
    logger.info("初始化完成：%s", summary)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    csv_path = sys.argv[1] if len(sys.argv) > 1 else str(CSV_DEFAULT)
    print(f"初始化数据库 {settings.dify_db_path} <- {csv_path}")
    summary = init_from_csv(csv_path)
    print("完成：", summary)


if __name__ == "__main__":
    main()
