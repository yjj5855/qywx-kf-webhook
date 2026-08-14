"""从「客户群列表_去重_公司ID回填.csv」提取群信息，匹配 Dify 中已存在的群专属知识库，
把知识库 dataset id 与公司ID回填到 group_bindings。

用法（仓库根目录）：
    python -m src.init_kb_bindings [csv路径]

- 知识库命名规范：群记忆_{group_id}（如 群记忆_G0004）
- 分页拉取 Dify 全部数据集（GET /v1/datasets）建立 name→id 映射
- 未匹配到知识库的群：保留原 memory_dataset_id（如有），并在结果中列出，可用
  `python -m src.init_datasets --with-company` 补建
- 幂等，可重复执行
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

import httpx

from src.binding import BindingStore, normalize_company_ids
from src.config import settings

logger = logging.getLogger(__name__)

DATASET_NAME_PREFIX = "群记忆_"
CSV_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "客户群列表_去重_公司ID回填.csv"


def fetch_all_datasets(base_url: str, api_key: str, page_size: int = 100) -> dict[str, str]:
    """分页拉取 Dify 全部数据集，返回 {数据集名称: 数据集ID}。"""
    name2id: dict[str, str] = {}
    page = 1
    headers = {"Authorization": f"Bearer {api_key}"}
    while True:
        url = f"{base_url.rstrip('/')}/v1/datasets?page={page}&limit={page_size}"
        resp = httpx.get(url, headers=headers, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        for d in data.get("data", []) or []:
            name = (d.get("name") or "").strip()
            if name:
                name2id[name] = d.get("id", "")
        if not data.get("has_more", False):
            break
        page += 1
    return name2id


def init_from_csv(csv_path: str | Path) -> dict:
    store = BindingStore(settings.dify_db_path)
    name2id = fetch_all_datasets(settings.dify_base_url, settings.dify_dataset_key)
    logger.info("已拉取 Dify 数据集 %d 个", len(name2id))

    matched = missing = inserted = updated = 0
    missing_groups: list[str] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            group_id = (row.get("群ID") or "").strip()
            if not group_id:
                continue
            group_name = (row.get("群名") or "").strip()
            company_ids = normalize_company_ids((row.get("公司ID") or "").strip())
            is_normal = (row.get("状态") or "").strip() == "正常"
            status = 1 if is_normal else 0

            existed = store.exists("wecom", group_id)
            existing = store.get_any("wecom", group_id) or {}

            dataset_id = name2id.get(f"{DATASET_NAME_PREFIX}{group_id}", "").strip()
            if not dataset_id:
                dataset_id = (existing.get("memory_dataset_id") or "").strip()

            store.upsert(
                platform="wecom",
                group_id=group_id,
                group_name=group_name,
                company_ids=company_ids,
                workflow_app_id=existing.get("workflow_app_id", "") or "",
                memory_dataset_id=dataset_id,
                status=status,
            )
            if existed:
                updated += 1
            else:
                inserted += 1
            if dataset_id:
                matched += 1
            else:
                missing += 1
                missing_groups.append(f"{group_id}({group_name})")

    summary = {
        "csv_total": inserted + updated,
        "inserted": inserted,
        "updated": updated,
        "kb_matched": matched,
        "kb_missing": missing,
        "missing_groups": missing_groups[:50],
        "missing_count": len(missing_groups),
    }
    logger.info("回填完成：%s", summary)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not settings.dify_dataset_key:
        print("未配置 WT_DIFY_DATASET_KEY，请先在 .env 配置【数据集权限】类型的 Key")
        sys.exit(1)
    csv_path = sys.argv[1] if len(sys.argv) > 1 else str(CSV_DEFAULT)
    print(f"回填数据库 {settings.dify_db_path} <- {csv_path}")
    summary = init_from_csv(csv_path)
    print("完成：", summary)
    if summary["kb_missing"]:
        print(f"提示：{summary['kb_missing']} 个群未匹配到「群记忆_*」知识库，"
              f"可执行 `python -m src.init_datasets --with-company` 补建")


if __name__ == "__main__":
    main()
