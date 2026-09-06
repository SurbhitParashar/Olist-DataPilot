from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    data_dir: str = '/data'
    db_path: str = '/data/app.db'
    mcp_url: str = 'http://mcp:8000/mcp'
    openrouter_api_key: str = ''
    openrouter_model: str = 'openrouter/free'
    agent_mode: str = 'llm'
    llm_timeout_seconds: float = 25.0
    tool_timeout_seconds: float = 15.0
    log_level: str = 'INFO'
    otel_enabled: bool = False


settings = Settings()
