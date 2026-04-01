"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "TradeSignal India v2"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tradesignal"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/tradesignal"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # NVIDIA NIM (Mistral Small 3.1 — fast + accurate)
    NIM_API_KEY: str = ""
    NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NIM_MODEL: str = "mistralai/mistral-small-3.1-24b-instruct-2503"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Scan settings
    DEFAULT_CAPITAL: float = 100000.0
    DEFAULT_MIN_CONFIDENCE: float = 65.0
    DEFAULT_MAX_POSITIONS: int = 5
    YFINANCE_CACHE_TTL: int = 900  # 15 minutes
    SCAN_RATE_LIMIT_PAUSE: float = 0.5  # seconds between batches
    SCAN_BATCH_SIZE: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
