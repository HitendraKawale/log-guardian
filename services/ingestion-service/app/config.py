"""Application configuration, loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # URL of the downstream AI analysis service.
    ai_service_url: str = "http://ai-service:8001"
    # Per-request timeout (seconds) when calling the AI service.
    ai_timeout: float = 2.0

    # SQLAlchemy async database URL. Defaults to a local SQLite file so the
    # service runs with zero external dependencies; Postgres is used in compose.
    database_url: str = "sqlite+aiosqlite:///./log_guardian.db"


settings = Settings()
