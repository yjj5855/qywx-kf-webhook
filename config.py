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
    intent_temperature: float = 1.0  # 温度参数（kimi-k2.5 仅支持 1.0）
    intent_confidence_threshold: float = 0.7  # 置信度阈值，低于此值视为 UNKNOWN

    # 群聊回复门控（为空则复用 intent 对应配置）
    gate_model: str = "kimi-k2.5"  # 门控专用模型，为空则用 intent_model
    gate_temperature: float = 1.0  # 门控温度参数


settings = Settings()
