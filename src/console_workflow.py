"""Dify 控制台工作流编辑工具：读取线上工作流 DSL → 本地修改 → 保存草稿并发布。

用法（仓库根目录，认证二选一）：
    # 导出指定应用的 DSL 到本地（先看现状）
    python -m src.console_workflow --app-id 8ac806cc-... --cookie "session=xxx" export -o dify/线上-开户办理-主流程.yml
    python -m src.console_workflow --app-id 8ac806cc-... --email a@b --password xxx export -o dify/xxx.yml

    # 把本地修改后的 DSL 推回线上（保存草稿 + 发布）
    python -m src.console_workflow --app-id 8ac806cc-... --cookie "session=xxx" draft dify/xxx.yml
    python -m src.console_workflow --app-id 8ac806cc-... --cookie "session=xxx" publish

    # 一步到位：导出 → 用本地文件替换 workflow 部分 → 发布
    python -m src.console_workflow --app-id 8ac806cc-... --cookie "session=xxx" apply dify/xxx.yml

说明：
- --cookie 为浏览器登录 Dify 后 F12 复制的会话 Cookie（形如 session=xxxx，可直接只传值）；
- 或者 --email/--password 用 POST /console/api/login 登录拿会话；
- draft 命令用本地 DSL 的 workflow（graph/features/environment_variables/conversation_variables）
  覆盖线上草稿，不触碰应用名/图标等 app 级字段；
- publish 命令发布当前草稿为线上版本（Dify 工作流需发布后 API 才生效）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

from src.config import settings

BASE_URL = "http://106.15.2.224"


def _console_url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}/console/api{path}"


def _make_client(cookie: str = "", email: str = "", password: str = "") -> httpx.AsyncClient:
    headers = {"User-Agent": "dsh-console-workflow/1.0"}
    cookies = httpx.Cookies()
    if cookie:
        raw = cookie.strip()
        if "=" not in raw:
            raw = f"session={raw}"
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies.set(k.strip(), v.strip())
    return httpx.AsyncClient(timeout=60.0, trust_env=False, cookies=cookies, headers=headers)


async def _ensure_login(client: httpx.AsyncClient, email: str, password: str) -> None:
    if not email:
        return
    resp = await client.post(_console_url("/login"), json={"email": email, "password": password})
    if resp.status_code != 200 or resp.json().get("code") != 0:
        raise RuntimeError(f"控制台登录失败：HTTP {resp.status_code} {resp.text[:300]}")


async def export_dsl(client: httpx.AsyncClient, app_id: str) -> str:
    resp = await client.get(_console_url(f"/apps/{app_id}/export"))
    if resp.status_code != 200:
        raise RuntimeError(f"导出失败：HTTP {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    dsl = data.get("data")
    if isinstance(dsl, str):
        return dsl
    if isinstance(dsl, dict):  # 兼容返回对象的情况
        return yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)
    raise RuntimeError(f"导出响应异常：{json.dumps(data, ensure_ascii=False)[:300]}")


async def get_app_info(client: httpx.AsyncClient, app_id: str) -> dict:
    resp = await client.get(_console_url(f"/apps/{app_id}"))
    if resp.status_code != 200:
        raise RuntimeError(f"读取应用信息失败：HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


async def save_draft(client: httpx.AsyncClient, app_id: str, workflow: dict) -> None:
    """用本地 workflow 对象覆盖线上草稿（graph/features/environment_variables/conversation_variables）。"""
    payload = {
        "graph": workflow.get("graph", {}),
        "features": workflow.get("features", {}),
        "environment_variables": workflow.get("environment_variables", []),
        "conversation_variables": workflow.get("conversation_variables", []),
        "annotated_config": workflow.get("annotated_config", {}),
    }
    resp = await client.post(_console_url(f"/apps/{app_id}/workflows/draft"), json=payload)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"保存草稿失败：HTTP {resp.status_code} {resp.text[:500]}")
    body = resp.json()
    if isinstance(body, dict) and body.get("code") not in (0, None):
        raise RuntimeError(f"保存草稿失败：{json.dumps(body, ensure_ascii=False)[:500]}")
    print(f"草稿已保存 app_id={app_id}")


async def publish(client: httpx.AsyncClient, app_id: str) -> None:
    resp = await client.post(_console_url(f"/apps/{app_id}/workflows/publish"), json={"remark": "dsh console 发布"})
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"发布失败：HTTP {resp.status_code} {resp.text[:500]}")
    print(f"已发布 app_id={app_id}")


def _load_local_workflow(path: str) -> dict:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    wf = d.get("workflow")
    if not isinstance(wf, dict):
        raise RuntimeError(f"{path} 缺少 workflow 顶层字段（不是 Dify 应用 DSL？）")
    return wf


async def run(args) -> None:
    client = _make_client(args.cookie, args.email, args.password)
    async with client:
        await _ensure_login(client, args.email, args.password)

        if args.cmd in ("export", "apply", "show"):
            dsl = await export_dsl(client, args.app_id)
            info = await get_app_info(client, args.app_id)
            name = "?"
            try:
                d = yaml.safe_load(dsl)
                name = d.get("app", {}).get("name", "?")
            except Exception:
                pass
            print(f"线上应用: {name}  app_id={args.app_id}  模式={info.get('data', {}).get('mode')}")
            if args.out:
                Path(args.out).write_text(dsl, encoding="utf-8")
                print(f"DSL 已导出到 {args.out}")
            else:
                print("---- DSL ----")
                print(dsl[:2000])

        if args.cmd in ("draft", "apply"):
            wf = _load_local_workflow(args.file)
            await save_draft(client, args.app_id, wf)

        if args.cmd in ("publish", "apply"):
            await publish(client, args.app_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dify 控制台工作流编辑工具")
    parser.add_argument("--app-id", required=True, help="Dify 应用 ID（URL 中的 UUID）")
    parser.add_argument("--base-url", default=BASE_URL, help="Dify 服务地址")
    parser.add_argument("--cookie", default="", help="浏览器登录后的会话 Cookie（可只传 session 值）")
    parser.add_argument("--email", default="", help="控制台登录邮箱")
    parser.add_argument("--password", default="", help="控制台登录密码")
    parser.add_argument("cmd", choices=["show", "export", "draft", "publish", "apply"])
    parser.add_argument("file", nargs="?", help="draft/apply 用：本地修改后的 DSL 文件路径")
    parser.add_argument("-o", "--out", default="", help="export 输出路径")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    if not args.cookie and not (args.email and args.password):
        print("缺少认证：--cookie 或 --email/--password 必填")
        sys.exit(2)
    if args.cmd in ("draft", "apply") and not args.file:
        print(f"{args.cmd} 需要本地 DSL 文件路径")
        sys.exit(2)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
