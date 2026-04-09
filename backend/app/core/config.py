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

    # --- Media storage (Фаза 4.5.2) ---
    # Корень файлового хранилища для MediaAsset. В Docker — /media
    # (named volume media-storage). Для локального запуска без Docker —
    # ./media в текущей директории backend'а. Реальное значение
    # переопределяется переменной окружения MEDIA_STORAGE_ROOT в compose.
    media_storage_root: str = "./media"
    # Hard-limit на размер одного файла в байтах (10 MB).
    media_max_file_size: int = 10 * 1024 * 1024

    # --- AI integration (Фаза 7, ADR-16) ---
    # Polza AI = OpenAI-совместимый прокси с оплатой в рублях, без VPN.
    # Используется через `openai` Python SDK (AsyncOpenAI) с кастомным
    # base_url. Дефолтные модели задаются в ai_service.py, не здесь —
    # здесь только credentials + endpoint. Ключ выдаётся в
    # polza.ai/dashboard/api-keys, в .env.example — пустой placeholder.
    # Пустое значение = AI-модуль отключён, ai_service поднимает
    # AIServiceUnavailableError, endpoint'ы в 7.2..7.8 отдают placeholder.
    polza_ai_api_key: str = ""
    polza_ai_base_url: str = "https://polza.ai/v1"
    # Timeout на один Polza вызов. ADR-16 фиксирует верхний лимит
    # Polza 600 сек; 60 сек — разумный дефолт для chat completions,
    # image generation (7.8) поднимет до 300 сек локально.
    polza_ai_timeout_seconds: float = 60.0
    # Количество retry внутри openai SDK при 5xx/connection errors.
    # Exponential backoff встроен в SDK, см. openai._base_client.
    polza_ai_max_retries: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        """Парсинг CSV в список: 'http://a,http://b' → ['http://a', 'http://b']."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
