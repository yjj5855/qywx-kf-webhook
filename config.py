from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "WT_",
        "env_file": str(Path(__file__).parent / ".env"),
        "extra": "ignore",
    }

    # 回调服务
    host: str = "0.0.0.0"
    port: int = 8000

    # WorkTool API 地址
    api_base_url: str = "https://api.worktool.ymdyes.cn"

    # AI 意图识别（OpenAI 兼容接口）
    intent_base_url: str = ""  # 接口基础地址（如 https://api.moonshot.cn/v1），为空则不启用
    intent_api_key: str = ""  # API 密钥
    intent_model: str = "kimi-k2.5"  # 模型名称
    intent_confidence_threshold: float = 0.7  # 置信度阈值，低于此值视为 UNKNOWN


settings = Settings()
