"""批量更新现有知识库设置：换 Embedding 模型 + 开启自动摘要（含自定义摘要提示词）。

背景（Dify 行为）：
- 知识库在创建时固化当时的 Embedding 模型；改"系统默认模型"不影响已有库，
  必须逐库把 embedding_model / embedding_model_provider 改成新模型；
- PATCH 改 embedding 模型（且与当前不同）会触发 Dify 后台自动重嵌入该库全部文档
  （deal_dataset_vector_index_task）；
- summary_index_setting（enable + model_name/model_provider_name + summary_prompt）
  保存后**不会**给已有文档生成摘要，只对新文档生效；已有文档需再调
  POST /console/api/datasets/{id}/documents/generate-summary 逐个生成。

用法（项目根目录，生产加 APP_ENV=prod）：
  # 1) 预览（不实际调用）
  APP_ENV=prod python -m src.update_kb_settings --dry-run \
      --embedding-model <新embedding模型名> --embedding-provider <供应商> \
      --summary-model <摘要用LLM模型名> --summary-provider <LLM供应商> \
      --summary-prompt "描述解决的问题,以中文生成,去除 think 内容" \
      --cookie "session=..."

  # 2) 正式执行：逐库 PATCH 换模型+开摘要 → 等重嵌入完成 → 触发摘要生成
  APP_ENV=prod python -m src.update_kb_settings \
      --embedding-model <...> --embedding-provider <...> \
      --summary-model <...> --summary-provider <...> \
      --summary-prompt "描述解决的问题,以中文生成,去除 think 内容" \
      --cookie "session=..."

认证二选一：
  --cookie "session=xxxx"      浏览器登录 Dify 后 F12 复制的会话 Cookie
  --email a@b --password xxx   脚本用 POST /console/api/login 登录拿会话

其他选项：
  --dataset-ids id1,id2        额外处理不在群绑定表里的知识库（如制度库），
                               与群知识库合并去重
  --only-embedding             只换 Embedding 模型，不动摘要设置
  --only-summary               只开摘要并生成，不换模型（模型已在别处处理）
  --wait-timeout 3600          等该库全部文档重嵌入完成的最长秒数；0=不等待
                               直接触发摘要生成（分段未就绪时会跳过）
  --wait-interval 10           轮询间隔（秒）
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys

import httpx

from src.binding import BindingStore
from src.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_PROMPT = (
    "用中文描述这段内容解决的问题，要求简洁、一两句话概括，不要使用编号列表或要点，"
    "不要输出思考过程、推理内容或 think 标签。"
)


def _console_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/console/api{path}"


def _service_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/v1{path}"


async def login(client: httpx.AsyncClient, base_url: str, email: str, password: str) -> None:
    """控制台登录：POST /console/api/login，会话 Cookie 由 httpx 自动保存。"""
    resp = await client.post(_console_url(base_url, "/login"), json={"email": email, "password": password})
    resp.raise_for_status()
    if resp.json().get("result") != "success":
        raise RuntimeError(f"控制台登录失败：{resp.text[:200]}")


async def patch_dataset(client: httpx.AsyncClient, base_url: str, dataset_id: str, payload: dict) -> None:
    resp = await client.patch(_console_url(base_url, f"/datasets/{dataset_id}"), json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"PATCH 数据集失败 HTTP {resp.status_code} body={resp.text[:300]}")
    resp.raise_for_status()


async def generate_summaries(
    client: httpx.AsyncClient, base_url: str, dataset_id: str, document_ids: list[str]
) -> None:
    resp = await client.post(
        _console_url(base_url, f"/datasets/{dataset_id}/documents/generate-summary"),
        json={"document_list": document_ids},
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"触发摘要生成失败 HTTP {resp.status_code} body={resp.text[:300]}"
        )
    resp.raise_for_status()


async def list_documents(base_url: str, api_key: str, dataset_id: str) -> list[dict]:
    """服务端 API 分页拉取数据集文档（含 indexing_status）。"""
    url = _service_url(base_url, f"/datasets/{dataset_id}/documents")
    headers = {"Authorization": f"Bearer {api_key}"}
    docs: list[dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as c:
        while True:
            resp = await c.get(url, params={"page": page, "limit": 100}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            docs.extend(data.get("data") or [])
            if not data.get("has_more") or page >= 100:
                break
            page += 1
    return docs


async def wait_documents_completed(
    base_url: str, api_key: str, dataset_id: str, timeout: int, interval: int
) -> tuple[bool, list[str]]:
    """轮询直到该库全部文档 indexing_status=completed；超时返回 False + 未完成文档名。"""
    waited = 0
    while True:
        docs = await list_documents(base_url, api_key, dataset_id)
        pending = [d for d in docs if d.get("indexing_status") not in ("completed", "error")]
        if not pending:
            errored = [d["name"] for d in docs if d.get("indexing_status") == "error"]
            return True, errored
        if timeout and waited >= timeout:
            return False, [d.get("name", "") for d in pending]
        await asyncio.sleep(interval)
        waited += interval


async def collect_dataset_ids(args) -> list[tuple[str, str]]:
    """群绑定库中的 (memory_dataset_id, group_id) + 命令行额外指定的数据集 ID，去重。"""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    store = BindingStore(settings.dify_db_path)
    for b in store.list():
        ds = (b.get("memory_dataset_id") or "").strip()
        if ds and ds not in seen:
            seen.add(ds)
            pairs.append((ds, (b.get("group_id") or "").strip()))
    if args.dataset_ids:
        for raw in re.split(r"[,，;；\s]+", args.dataset_ids):
            raw = raw.strip()
            if raw and raw not in seen:
                seen.add(raw)
                pairs.append((raw, ""))
    return pairs


async def get_dataset_detail(api_key: str, base_url: str, dataset_id: str) -> dict:
    """服务端 API 读数据集详情（当前 embedding 模型 / 索引方式 / 摘要设置），无需控制台会话。"""
    url = _service_url(base_url, f"/datasets/{dataset_id}")
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as c:
        resp = await c.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code >= 400:
            raise RuntimeError(f"GET 数据集详情失败 HTTP {resp.status_code} body={resp.text[:300]}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") if isinstance(data, dict) and "data" in data else data


def _fmt_summary(s: dict | None) -> str:
    s = s or {}
    if not s.get("enable"):
        return "未开启"
    return (
        f"开启(model={s.get('model_provider_name')}/{s.get('model_name')}, "
        f"prompt={s.get('summary_prompt') or '（默认）'})"
    )


def print_current(detail: dict) -> None:
    print(
        f"  当前: indexing={detail.get('indexing_technique')}, "
        f"embedding={detail.get('embedding_model_provider')}/{detail.get('embedding_model')}, "
        f"摘要={_fmt_summary(detail.get('summary_index_setting'))}"
    )


def print_planned(args, dataset_id: str) -> None:
    parts = []
    if not args.only_summary and args.embedding_model and args.embedding_provider:
        parts.append(
            f"embedding={args.embedding_provider}/{args.embedding_model}"
            f"（触发该库全部文档自动重嵌入）"
        )
    if not args.only_embedding and args.summary_model and args.summary_provider:
        parts.append(
            f"摘要=开启(model={args.summary_provider}/{args.summary_model}, "
            f"prompt={args.summary_prompt!r})"
        )
    if parts:
        print(f"  [dry-run] 将改为: {'; '.join(parts)}")
    else:
        print("  [dry-run] 未提供新配置参数，仅列出当前配置")


async def run(args) -> None:
    base_url = settings.dify_base_url
    if not settings.dify_dataset_key:
        print("未配置 WT_DIFY_DATASET_KEY，请先在 .env 配置【数据集权限】类型的 Key")
        sys.exit(1)

    if not args.only_embedding and not (args.summary_model and args.summary_provider) and not args.dry_run:
        print("缺少摘要 LLM 配置：--summary-model / --summary-provider 必填（--only-embedding 或 --dry-run 时可省略）")
        sys.exit(1)
    if not args.only_summary and not (args.embedding_model and args.embedding_provider) and not args.dry_run:
        print("缺少新 Embedding 模型配置：--embedding-model / --embedding-provider 必填（--only-summary 或 --dry-run 时可省略）")
        sys.exit(1)
    if not args.cookie and not (args.email and args.password) and not args.dry_run:
        print("缺少认证：--cookie 或 --email/--password 必填（dry-run 只读配置，可省略）")
        sys.exit(1)

    dataset_pairs = await collect_dataset_ids(args)
    print(f"将处理 {len(dataset_pairs)} 个知识库（dry_run={args.dry_run}）")

    # 读取当前配置用服务端 API（数据集 Key 即可）；写操作用控制台 API（需登录会话）
    cookies = httpx.Cookies()
    csrf_token = ""
    if args.cookie:
        raw = args.cookie.strip()
        if raw and "=" not in raw:
            raw = f"session={raw}"
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            k, _, v = part.partition("=")
            cookies.set(k.strip(), v.strip())
            if k.strip() == "csrf_token":
                csrf_token = v.strip()
    headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}

    console_client = None
    if not args.dry_run:
        console_client = httpx.AsyncClient(
            timeout=60.0, trust_env=False, cookies=cookies, follow_redirects=False, headers=headers
        )
        if args.email:
            await login(console_client, base_url, args.email, args.password)
            print("控制台登录成功")

    ok = failed = 0
    try:
        for idx, (ds, group_id) in enumerate(dataset_pairs, start=1):
            label = f"[{idx}/{len(dataset_pairs)}]"
            if group_id:
                label += f" {group_id}"
            try:
                detail = await get_dataset_detail(settings.dify_dataset_key, base_url, ds)
                print(f"{label} 知识库 {ds}（{detail.get('name') or '?'}）")
                print_current(detail)
                if args.dry_run:
                    print_planned(args, ds)
                    ok += 1
                    continue

                payload: dict = {}
                embedding_changed = False
                if not args.only_summary:
                    payload["embedding_model"] = args.embedding_model
                    payload["embedding_model_provider"] = args.embedding_provider
                    embedding_changed = True
                if not args.only_embedding:
                    payload["summary_index_setting"] = {
                        "enable": True,
                        "model_name": args.summary_model,
                        "model_provider_name": args.summary_provider,
                        "summary_prompt": args.summary_prompt,
                    }
                print(f"  更新: {payload}")
                await patch_dataset(console_client, base_url, ds, payload)

                # 换模型后等该库全部文档重嵌入完成，再触发摘要（分段未就绪会跳过）
                if embedding_changed and args.wait_timeout and not args.skip_summary_trigger:
                    done, errored = await wait_documents_completed(
                        base_url, settings.dify_dataset_key, ds, args.wait_timeout, args.wait_interval
                    )
                    if not done:
                        print(f"  ⚠ 等待重嵌入超时（{args.wait_timeout}s），跳过摘要触发 {ds}；"
                              f"稍后可加 --only-summary 重跑")
                        ok += 1
                        continue
                    if errored:
                        print(f"  ⚠ 有文档重嵌入出错：{errored}，仍继续触发摘要")

                if not args.only_embedding and not args.skip_summary_trigger:
                    docs = await list_documents(base_url, settings.dify_dataset_key, ds)
                    doc_ids = [d["id"] for d in docs if d.get("id") and d.get("doc_form") != "qa_model"]
                    if not doc_ids:
                        print(f"  - 知识库 {ds} 无文档，跳过摘要生成")
                    else:
                        await generate_summaries(console_client, base_url, ds, doc_ids)
                        print(f"  ✓ 已触发 {len(doc_ids)} 个文档的摘要生成")
                ok += 1
            except Exception as exc:
                logger.exception("处理知识库失败 dataset=%s", ds)
                print(f"  ✗ 处理失败 {ds}: {exc}")
                failed += 1
    finally:
        if console_client is not None:
            await console_client.aclose()
    print(f"完成：成功 {ok}，失败 {failed}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="批量更新现有知识库：换 Embedding 模型 + 开自动摘要")
    parser.add_argument("--dry-run", action="store_true",
                        help="只读每个知识库当前配置并显示将做的修改，不实际调用")
    parser.add_argument("--cookie", default="", help="Dify 控制台会话 Cookie（浏览器 F12 复制，如 session=xxx）")
    parser.add_argument("--email", default="", help="Dify 管理员账号（与 --password 二选一于 --cookie）")
    parser.add_argument("--password", default="", help="Dify 管理员密码")
    parser.add_argument("--embedding-model", default="", help="新 Embedding 模型名")
    parser.add_argument("--embedding-provider", default="", help="新 Embedding 模型供应商")
    parser.add_argument("--summary-model", default="", help="摘要生成用 LLM 模型名（Dify 里已配置）")
    parser.add_argument("--summary-provider", default="", help="摘要生成用 LLM 供应商")
    parser.add_argument("--summary-prompt", default=DEFAULT_SUMMARY_PROMPT, help="摘要生成提示词")
    parser.add_argument("--dataset-ids", default="", help="额外数据集 ID（逗号分隔），如制度库")
    parser.add_argument("--only-embedding", action="store_true", help="只换 Embedding 模型")
    parser.add_argument("--only-summary", action="store_true", help="只开摘要并生成，不换模型")
    parser.add_argument("--skip-summary-trigger", action="store_true",
                        help="只 PATCH 配置（换模型+摘要设置），不触发摘要生成；"
                             "用于先批量更新全部库，等重嵌入完成后再用 --only-summary 统一生成摘要")
    parser.add_argument("--wait-timeout", type=int, default=3600, help="等重嵌入完成超时秒数（0=不等待）")
    parser.add_argument("--wait-interval", type=int, default=10, help="重嵌入轮询间隔秒数")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
