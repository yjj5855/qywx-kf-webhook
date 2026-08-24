"""仅同步公司ID到 group_bindings.company_ids（最小更新，不触碰其他列）。

用法（仓库根目录）：
    python -m src.update_company_ids [csv路径]   # 默认 docs/客户群列表_公司ID更新.csv

CSV 列：群ID, 公司ID
设计：
- 只更新 company_ids（及 updated_at），不覆盖 group_name / status /
  workflow_app_id / memory_dataset_id / kb_last_export_id，
  避免 CSV 其他列与服务器数据不一致时被误写。
- 按 platform='wecom' + group_id 定位；库里不存在的群跳过并告警，不新增。
- 空公司ID行跳过（避免误清空库里已有值）；多公司ID任意分隔符统一归一化为顿号。
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

from src.binding import BindingStore, normalize_company_ids
from src.config import settings

logger = logging.getLogger(__name__)

CSV_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "客户群列表_公司ID更新.csv"


def update_from_csv(csv_path: str | Path = CSV_DEFAULT) -> dict:
    store = BindingStore(settings.dify_db_path)
    updated = skipped_empty = missing = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            group_id = (row.get("群ID") or "").strip()
            company_ids = (row.get("公司ID") or "").strip()
            if not group_id:
                continue
            if not company_ids:
                skipped_empty += 1
                continue
            if store.update_company_ids(
                "wecom", group_id, normalize_company_ids(company_ids)
            ):
                updated += 1
            else:
                missing += 1
                logger.warning("群 %s 不在库中，已跳过", group_id)

    summary = {"updated": updated, "skipped_empty": skipped_empty, "missing": missing}
    logger.info("公司ID更新完成：%s", summary)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    csv_path = sys.argv[1] if len(sys.argv) > 1 else str(CSV_DEFAULT)
    print(f"更新数据库 {settings.dify_db_path} <- {csv_path}")
    summary = update_from_csv(csv_path)
    print("完成：", summary)


if __name__ == "__main__":
    main()
