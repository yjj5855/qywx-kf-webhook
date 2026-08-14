from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "WT_",
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "extra": "ignore",
    }

    # 回调服务
    host: str = "0.0.0.0"
    port: int = 8000

    # WorkTool API 地址
    api_base_url: str = "https://api.worktool.ymdyes.cn"

    # ---- Dify 主工作流（回调 → 整理参数 → /v1/workflows/run）----
    dify_base_url: str = "http://192.168.31.204"        # Dify 服务地址，如 http://192.168.31.204
    # 主工作流「WorkTool 回调消息处理」的 API Key（敏感，配置在 .env: WT_DIFY_WORKFLOW_KEY）
    dify_workflow_key: str = ""
    dify_timeout: float = 30.0     # 工作流调用超时（秒）
    # 会话会话ID/群绑定 的本地 SQLite 存储路径
    dify_db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "app.db")

    # ---- 公司信息查询（应用层执行：用群绑定 company_ids 调公司接口）----
    company_api_base_url: str = ""  # 公司数据网关地址，如 https://company-gateway.example.com
    company_api_key: str = ""       # 公司数据网关密钥（可选）

    # ---- 知识库（群聊天记录 → Dify 数据集）----
    # Dify「API 访问」页创建的"数据集"权限类型 API Key（敏感，配置在 .env: WT_DIFY_DATASET_KEY）
    dify_dataset_key: str = ""
    # 知识库增量导出定时任务间隔（秒），0=关闭定时导出（可手动调 /api/messages/export）
    dify_export_interval: float = 300.0
    # 知识库索引方式：economy=关键词索引（免向量模型，默认）/ high_quality=语义索引（需 Dify 配置 Embedding 模型）
    dify_dataset_indexing: str = "economy"


settings = Settings()
