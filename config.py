from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "WT_", "env_file": ".env", "extra": "ignore"}

    # 回调服务
    host: str = "0.0.0.0"
    port: int = 8000

    # WorkTool API 地址
    api_base_url: str = "https://api.worktool.ymdyes.cn"


settings = Settings()
