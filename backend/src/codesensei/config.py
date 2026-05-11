"""Environment-driven settings (read by every other module)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://codesensei:codesensei@postgres:5432/codesensei"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"

    llm_provider: str = "openai"
    embedding_provider: str = "openai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    llm_model: str = ""
    embedding_model: str = ""
    ollama_base_url: str = "http://ollama:11434"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
