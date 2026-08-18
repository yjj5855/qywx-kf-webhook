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

    # ---- Dify 主工作流（回调 → 整理参数 → /v1/workflows/run）----
    dify_base_url: str = "http://192.168.31.204"        # Dify 服务地址，如 http://192.168.31.204
    # 主工作流「WorkTool 回调消息处理」的 API Key（敏感，配置在 .env 文件: WT_DIFY_WORKFLOW_KEY）
    dify_workflow_key: str = ""
    dify_timeout: float = 30.0     # 工作流调用超时（秒）
    # 会话会话ID/群绑定 的本地 SQLite 存储路径
    dify_db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "app.db")

    # ---- 知识库（群聊天记录 → Dify 数据集）----
    # Dify「API 访问」页创建的"数据集"权限类型 API Key（敏感，配置在 .env 文件: WT_DIFY_DATASET_KEY）
    dify_dataset_key: str = ""
    # 知识库每日同步时间（北京时间 HH:MM，如 01:00），空串=关闭定时同步（仅手动调 /api/messages/sync）
    dify_export_time: str = "01:00"
    # 知识库索引方式：economy=关键词索引（免向量模型，默认）/ high_quality=语义索引（需 Dify 配置 Embedding 模型）
    dify_dataset_indexing: str = "economy"


settings = Settings()
