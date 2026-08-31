"""群公司档案：把客服手写的「群-公司信息描述」同步进群专属知识库。

工作流：
1. 客服在 company_profile_dir（默认 docs/公司档案）维护每个群的 Markdown 描述，
   文件名固定为 {group_id}.md（如 G0115.md）。模板由 sync_company_profiles --init
   生成（群信息 + 各公司块预填，公司名从群名启发式解析，最终以客服填写为准）；
2. `python -m src.sync_company_profiles` 把每个已存在的档案文件同步到该群知识库
   （memory_dataset_id），文档名固定为 群档案_{group_id}：先删同名旧文档再重建，
   保证知识库里始终只有一份最新档案，与每日对话流水（群对话_*）互不干扰；
3. 群绑定变更（POST /api/bindings）时自动尝试同步该群档案（缺档案/缺知识库则跳过）。

设计要点（群知识库为向量索引 high_quality，QA 检索 semantic_search）：
- 每个公司一块（### 公司N：名称（公司ID）），块首为完整自然语言句，
  语义检索整块命中；块间空行分隔，保证每块独立分块；
- 头部「## 公司清单」一句话列全公司名，回答"这个群服务哪些公司"类问题；
- 一个群对应多家公司：块按 company_ids 顺序固定编号，数量与绑定一致；
- 对客服的写作要求见 docs/公司档案写作规范.md。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from src.config import settings
from src.kb import create_dataset_document

logger = logging.getLogger(__name__)

PROFILE_PREFIX = "群档案_"          # 知识库中文档名前缀，如 群档案_G0115
PROFILE_FILE_SUFFIX = ".md"         # 客服档案文件后缀

# 群名解析时过滤掉的非公司词（仅用于模板预填，不参与同步内容判断）
_BLOCKLIST = {"群聊", "测试", "测试群", "内部群"}


# ---- 文件路径 ----

def profile_dir() -> Path:
    """档案目录（配置为相对路径时按项目根目录解析）。"""
    p = Path(settings.company_profile_dir)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    return p


def profile_path(group_id: str) -> Path:
    return profile_dir() / f"{group_id}{PROFILE_FILE_SUFFIX}"


def read_profile(group_id: str) -> str | None:
    """读取档案文本；文件不存在返回 None，存在但为空返回 ""（表示从知识库移除）。"""
    p = profile_path(group_id)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def write_profile(group_id: str, text: str) -> Path:
    p = profile_path(group_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---- 文本构建 ----

def parse_company_names(group_name: str) -> list[str]:
    """从群名启发式解析公司名（仅用于生成模板预填，最终以客服填写为准）。

    规则：去掉尾部（异地），取第一个 - 之前的部分（群名通常形如
    "商图信息/柏奥会科技/滴图信息-小步人事服务群"），再按 /、& 等分隔符切分；
    解析不出或全为占位词时返回空列表。
    """
    name = (group_name or "").strip()
    name = re.sub(r"[（(]\s*异地\s*[)）]$", "", name)
    head = re.split(r"[-－]", name, maxsplit=1)[0]
    parts = [p.strip() for p in re.split(r"[/、&,，;|]", head) if p.strip()]
    return [p for p in parts if p not in _BLOCKLIST]


def build_profile_template(binding: dict) -> str:
    """生成一份可交给客服填写的档案模板（向量知识库友好结构）。

    群信息 + 每个公司一块；公司块按 company_ids 顺序编号，公司名尽量从群名预填，
    其余字段留占位符。未绑定公司ID时只输出群信息并提示。
    """
    group_id = (binding.get("group_id") or "").strip()
    group_name = (binding.get("group_name") or "").strip()
    company_ids = [c.strip() for c in re.split(r"[、,;]", binding.get("company_ids") or "") if c.strip()]
    names = parse_company_names(group_name)

    lines = [
        # 注意：不要以单个 "# "（一级标题）开头——Dify 解析文档时会剥掉行首的一级标题
        # 标记（"# xxx" → "xxx"，"##"/"###" 不受影响），文档名（群档案_{group_id}）
        # 本身已是标题，这里用普通段落开场，避免标题被剥、也保留语义锚点。
        f"本档案描述群 {group_id}（{group_name}）对应的客户公司信息，供客服回答公司类问题时参考。",
        "",
        "## 群信息",
        f"- 群ID：{group_id}",
        f"- 群名：{group_name}",
        f"- 绑定公司数：{len(company_ids) if company_ids else '未绑定'}",
        "",
    ]

    if not company_ids:
        lines += [
            "## 公司清单",
            "本群暂未绑定公司ID，请在群绑定中补充公司ID后重新生成模板填写。",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## 公司清单",
        f"本群对应以下 {len(company_ids)} 家公司：",
        "",
    ]
    for i, cid in enumerate(company_ids, start=1):
        name = names[i - 1] if i - 1 < len(names) else ""
        display = name or "（公司名称待填写）"
        lines += [
            f"### 公司{i}：{display}（公司ID：{cid}）",
            f"{display}是本群对应的客户公司，服务内容为（待填写：人事外包 / 社保公积金代缴 / 招聘 / 代发工资等）。",
            "- 公司全称：（待填写，如“上海XX信息科技有限公司”）",
            "- 常用称呼：（待填写，客户在群里怎么叫就写什么，如“商图”）",
            "- 服务内容：（待填写，一句话说明为该客户提供哪些服务）",
            "- 联系人/对接人：（待填写，可选；涉及个人隐私请谨慎）",
            "- 备注：（待填写，账期、特殊约定等；敏感信息不写）",
            "",
        ]
    return "\n".join(lines)


# ---- Dify 文档管理 ----

def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def list_documents(
    base_url: str, api_key: str, dataset_id: str, timeout: float = 30.0
) -> list[dict]:
    """列出数据集全部文档（分页拉取，返回文档 dict 列表，含 id/name）。"""
    url = f"{base_url.rstrip('/')}/v1/datasets/{dataset_id}/documents"
    docs: list[dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=timeout, trust_env=settings.httpx_trust_env) as client:
        while True:
            resp = await client.get(
                url, params={"page": page, "limit": 100}, headers=_headers(api_key)
            )
            resp.raise_for_status()
            data = resp.json()
            docs.extend(data.get("data") or [])
            if not data.get("has_more") or page >= 100:
                break
            page += 1
    return docs


async def delete_document(
    base_url: str, api_key: str, dataset_id: str, document_id: str, timeout: float = 30.0
) -> dict:
    url = f"{base_url.rstrip('/')}/v1/datasets/{dataset_id}/documents/{document_id}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=settings.httpx_trust_env) as client:
        resp = await client.delete(url, headers=_headers(api_key))
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            # 部分 Dify 版本 DELETE 成功但返回空 body，此时 HTTP 200 即视为成功
            return {"result": "success"}


async def sync_profile(binding: dict, text: str) -> dict:
    """把档案文本同步进该群知识库：删同名旧文档 → 重建一份，幂等。

    text 为空（档案文件存在但被清空）时只删不建，表示从知识库移除该档案。
    """
    group_id = (binding.get("group_id") or "").strip()
    dataset_id = (binding.get("memory_dataset_id") or "").strip()
    name = f"{PROFILE_PREFIX}{group_id}"
    deleted: list[str] = []

    for doc in await list_documents(settings.dify_base_url, settings.dify_dataset_key, dataset_id):
        if doc.get("name") == name:
            try:
                await delete_document(settings.dify_base_url, settings.dify_dataset_key, dataset_id, doc["id"])
                deleted.append(doc["id"])
                logger.info("删除旧档案文档 group=%s doc=%s", group_id, doc["id"])
            except Exception:
                logger.exception("删除旧档案文档失败 group=%s doc=%s", group_id, doc.get("id"))

    text = (text or "").strip()
    if not text:
        return {"synced": False, "removed": True, "deleted": deleted}

    resp = await create_dataset_document(
        settings.dify_base_url, settings.dify_dataset_key, dataset_id, name, text
    )
    return {"synced": True, "removed": False, "document_id": (resp or {}).get("id") or "", "deleted": deleted}


async def sync_group_profile(platform: str, group_id: str) -> dict | None:
    """按群同步档案（API 钩子与脚本共用的单群入口）。

    无绑定 / 未绑定知识库 / 无档案文件 → 返回 None（跳过）；
    否则同步，并保证异常不外抛（记录日志），方便调用方 fire-and-forget。
    """
    from src.binding import BindingStore

    try:
        if not settings.dify_dataset_key:
            logger.warning("未配置 WT_DIFY_DATASET_KEY，跳过群公司档案同步")
            return None
        binding = BindingStore(settings.dify_db_path).get(platform, group_id)
        if not binding or not (binding.get("memory_dataset_id") or "").strip():
            return None
        text = read_profile(group_id)
        if text is None:
            return None
        result = await sync_profile(binding, text)
        logger.info("群公司档案同步完成 group=%s result=%s", group_id, result)
        return result
    except Exception:
        logger.exception("群公司档案同步失败 platform=%s group=%s", platform, group_id)
        return None
