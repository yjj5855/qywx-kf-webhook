import os
from pathlib import Path

from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent.parent

# 运行环境通过 APP_ENV 指定（默认 dev），加载对应的 .env.{APP_ENV} 文件；
# 指定文件不存在时回退到 .env。
APP_ENV = os.getenv("APP_ENV", "dev").strip().lower() or "dev"
_ENV_FILE = _BASE_DIR / f".env.{APP_ENV}"
if not _ENV_FILE.exists():
    _ENV_FILE = _BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "WT_",
        "env_file": str(_ENV_FILE),
        "extra": "ignore",
    }

    # 回调服务
    host: str = "0.0.0.0"
    port: int = 8000

    # WorkTool API 地址
    api_base_url: str = "https://api.worktool.ymdyes.cn"

    # 回调防抖：同一会话在窗口（秒）内的多条消息合并为一次工作流调用（只处理最新一条，
    # 但所有消息仍会入库）；处理期间到达的消息串行排队不并发。0=关闭防抖（仍串行）。
    debounce_seconds: float = 1.0

    # ---- Dify 工作流（回调 → 整理参数 → /v1/workflows/run）----
    dify_base_url: str = "http://192.168.31.204"        # Dify 服务地址，如 http://192.168.31.204
    # 注意：Dify 工作流应用的 API Key 不再放配置文件 —— 它跟着 workflow appid 走，
    # 每个群在群绑定表 group_bindings.workflow_app_id 列配置自己工作流的 Key（app-xxx），
    # handler 直接取该值调用对应工作流应用；群未绑定 workflow_app_id 则不调用工作流。
    dify_timeout: float = 30.0     # 工作流调用超时（秒）
    # 会话会话ID/群绑定 的本地 SQLite 存储路径
    dify_db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "app.db")

    # ---- 知识库（群聊天记录 → Dify 数据集）----
    # Dify「API 访问」页创建的"数据集"权限类型 API Key（敏感，配置在 .env 文件: WT_DIFY_DATASET_KEY）
    dify_dataset_key: str = ""
    # 知识库每日同步时间（北京时间 HH:MM，如 23:30），空串=关闭定时同步（仅手动调 /api/messages/sync）
    # 建议放在当天结束前（如 23:30），使文档名日期与当天聊天日期一致
    dify_export_time: str = "23:30"
    # 知识库索引方式：economy=关键词索引（免向量模型，默认）/ high_quality=语义索引（需 Dify 配置 Embedding 模型）
    dify_dataset_indexing: str = "economy"
    # 群公司档案目录（相对项目根目录或绝对路径）：客服手写的群-公司信息描述
    # Markdown 文件存放处，每群一个 {group_id}.md，由 src.sync_company_profiles 同步进群知识库
    company_profile_dir: str = "docs/公司档案"

    # ---- 语雀外部知识库（Dify 外部知识库胶水服务，POST /retrieval）----
    # 语雀团队令牌（https://www.yuque.com/settings/tokens 获取，敏感，配置在 .env 文件: WT_YUQUE_TOKEN）
    yuque_token: str = ""
    # Dify「连接外部知识库」时填写的 API Key（与 Dify 配置一致，敏感，配置在 .env 文件: WT_YUQUE_EXTERNAL_KEY）
    yuque_external_key: str = ""
    # 语雀开放 API 基础地址（企业版改成 https://{企业域名}.yuque.com/api/v2）
    yuque_api_base: str = "https://www.yuque.com/api/v2"
    # 默认搜索范围，形如 "团队login/知识库slug"（如 myteam/mywiki）；留空=搜索当前账号可见的全部内容
    yuque_scope: str = ""
    # 外部知识库 ID → 语雀搜索范围 的映射（JSON），如 {"yuque-wiki": "myteam/mywiki"}，
    # 让 Dify 里不同的"外部知识库 ID"各自限定到不同语雀知识库；未匹配到该 ID 时回退 yuque_scope
    yuque_kb_scopes: str = "{}"


settings = Settings()
