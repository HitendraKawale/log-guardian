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

    # Comma-separated list of origins allowed to call the API from a browser
    # (the web dashboard). Defaults to any origin for easy local development.
    cors_allow_origins: str = "*"

    # When set, every /logs request must carry this value in the X-API-Key
    # header. Empty (the default) leaves the API open for local development.
    api_key: str = ""

    # Per-client-IP request cap per minute. 0 disables rate limiting.
    rate_limit_per_minute: int = 0

    # Kafka streaming (optional). When disabled, the synchronous REST path is
    # the only way logs are ingested.
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic: str = "logs.raw"
    kafka_consumer_group: str = "log-scorer"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",")]


settings = Settings()
