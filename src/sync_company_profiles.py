"""群公司档案运维脚本：生成客服填写模板 / 同步到群知识库 / 清理过期档案。

用法（仓库根目录）：
    python -m src.sync_company_profiles               # 同步已有档案文件到群知识库
    python -m src.sync_company_profiles --init        # 为缺档案的有公司绑定群生成模板（不同步）
    python -m src.sync_company_profiles --init --force# 重新生成并覆盖已有模板
    python -m src.sync_company_profiles --dry-run     # 只打印将执行的动作，不实际执行
    python -m src.sync_company_profiles --prune       # 删除"无档案文件"群的残留档案文档

流程说明（详见 docs/公司档案写作规范.md）：
1. --init 生成模板文件 docs/公司档案/{group_id}.md（仅含公司ID的群）；
2. 客服按写作规范填写各公司块；
3. 不带参数执行：把每个存在档案文件的群同步到其知识库（文档名 群档案_{group_id}，
   删同名旧文档后重建，幂等）；档案文件存在但被清空 = 从知识库移除该档案；
4. --prune：清理档案文件已被删除、但知识库里还残留 群档案_* 文档的群（需先绑定知识库）。
"""
from __future__ import annotations

import asyncio
import logging
import sys

from src.binding import BindingStore
from src.company_profile import (
    build_profile_template,
    list_documents,
    profile_path,
    read_profile,
    sync_profile,
)
from src.config import settings

logger = logging.getLogger(__name__)


def generate_templates(force: bool = False, dry_run: bool = False) -> dict:
    """为已绑定公司ID且缺档案（或 --force）的群生成模板文件。"""
    store = BindingStore(settings.dify_db_path)
    generated = skipped = 0
    for b in store.list():
        group_id = (b.get("group_id") or "").strip()
        company_ids = (b.get("company_ids") or "").strip()
        if not group_id or not company_ids:
            continue  # 未绑定公司ID的群不生成（公司信息无从描述）
        p = profile_path(group_id)
        if p.exists() and not force:
            skipped += 1
            continue
        text = build_profile_template(b)
        if dry_run:
            print(f"[dry-run] 生成模板 {p}")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            logger.info("生成档案模板 group=%s -> %s", group_id, p)
        generated += 1
    return {"generated": generated, "skipped": skipped}


async def sync_all(dry_run: bool = False) -> dict:
    """把所有存在档案文件且绑定了知识库的群同步到 Dify。"""
    store = BindingStore(settings.dify_db_path)
    results: dict[str, str] = {}
    for b in store.list():
        group_id = (b.get("group_id") or "").strip()
        dataset_id = (b.get("memory_dataset_id") or "").strip()
        if not group_id or not dataset_id:
            continue
        text = read_profile(group_id)
        if text is None:
            continue  # 客服还没写，跳过
        if dry_run:
            action = "移除" if not text.strip() else "同步"
            results[group_id] = f"[dry-run] {action} -> 群档案_{group_id}"
            continue
        result = await sync_profile(b, text)
        results[group_id] = (
            f"removed={result['removed']}" if result["removed"]
            else f"synced doc={result['document_id'] or '?'}"
        )
        logger.info("同步群公司档案 group=%s %s", group_id, results[group_id])
    return results


async def prune_stale(dry_run: bool = False) -> dict:
    """删除"档案文件已不存在"的群在知识库里的残留 群档案_* 文档。"""
    store = BindingStore(settings.dify_db_path)
    removed = skipped = 0
    for b in store.list():
        group_id = (b.get("group_id") or "").strip()
        dataset_id = (b.get("memory_dataset_id") or "").strip()
        if not group_id or not dataset_id:
            continue
        if profile_path(group_id).exists():
            continue
        name = f"群档案_{group_id}"
        try:
            docs = [
                d for d in await list_documents(
                    settings.dify_base_url, settings.dify_dataset_key, dataset_id
                )
                if d.get("name") == name
            ]
        except Exception:
            logger.exception("列出文档失败 group=%s", group_id)
            continue
        for d in docs:
            if dry_run:
                print(f"[dry-run] 删除残留档案文档 group={group_id} doc={d['id']} name={name}")
            else:
                from src.company_profile import delete_document
                await delete_document(
                    settings.dify_base_url, settings.dify_dataset_key, dataset_id, d["id"]
                )
                logger.info("删除残留档案文档 group=%s doc=%s", group_id, d["id"])
            removed += 1
        if not docs:
            skipped += 1
    return {"removed": removed, "no_stale": skipped}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    flags = set(sys.argv[1:])
    dry_run = "--dry-run" in flags
    want_init = "--init" in flags
    want_prune = "--prune" in flags
    force = "--force" in flags

    if not settings.dify_dataset_key:
        print("未配置 WT_DIFY_DATASET_KEY，请先在 .env 配置【数据集权限】类型的 Key")
        sys.exit(1)

    if want_init:
        print(f"生成档案模板目录：{profile_path('x').parent}（dry_run={dry_run}）")
        print("模板生成：", generate_templates(force=force, dry_run=dry_run))

    if want_prune:
        print("清理残留档案文档：", asyncio.run(prune_stale(dry_run=dry_run)))

    if not want_init and not want_prune:
        print("同步群公司档案到知识库（dry_run=%s）：" % dry_run)
        results = asyncio.run(sync_all(dry_run=dry_run))
        print(f"完成：共 {len(results)} 个群，明细：")
        for gid, r in sorted(results.items()):
            print(f"  {gid}: {r}")


if __name__ == "__main__":
    main()
