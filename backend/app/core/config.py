"""Конфигурация приложения через pydantic-settings.

Переменные читаются из окружения. Для локальной разработки без Docker —
из `.env` в корне backend'а. В Docker compose — из секции `environment`.

Значения-defaults ниже предназначены только для локального запуска без .env
и не должны использоваться в продакшене (SECRET_KEY, пароли БД и т.п.).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database (используется начиная с задачи 0.3) ---
    database_url: str = (
        "postgresql+asyncpg://dbuser:dbpassword@localhost:5432/dbpassport"
    )

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- Security / JWT (используется с задачи 1.1) ---
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # --- Application ---
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Парсинг CSV в список: 'http://a,http://b' → ['http://a', 'http://b']."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
