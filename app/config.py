import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

IS_VERCEL = os.getenv('VERCEL') == '1'
ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    data_dir: str = './data'
    db_path: str = '/tmp/olist-app.db' if IS_VERCEL else './data/app.db'
    mcp_url: str = 'inprocess' if IS_VERCEL else 'http://mcp:8000/mcp'
    openrouter_api_key: str = ''
    openrouter_model: str = 'openrouter/free'
    agent_mode: str = 'llm'
    llm_timeout_seconds: float = 25.0
    tool_timeout_seconds: float = 15.0
    log_level: str = 'INFO'
    otel_enabled: bool = False


settings = Settings()
