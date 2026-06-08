from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    ANTHROPIC_API_KEY: str | None = None

    IMAGE_DIR: str = "images"

    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_ENGINE: str = "gemini"
    ANALYSIS_SAMPLES: int = 3
    AI_MAX_CONCURRENT: int = 10

    REDIS_URL: str = "redis://localhost:6379"

    # Comma-separated allowed origins, or "*" for any (dev only).
    # Note: "*" forces allow_credentials=False — the combination is invalid per CORS spec.
    CORS_ORIGINS: str = "*"

    # Auth — when set, all /api/analyze and /api/jobs routes require this key
    # via `Authorization: Bearer <key>` (HTTP) or `?token=<key>` (WebSocket).
    # Leave unset to disable auth (dev only).
    API_KEY: str | None = None

    # Trust X-Forwarded-For for client IP (enable ONLY behind a proxy/LB you
    # control — otherwise clients can spoof the header to bypass rate limiting).
    TRUST_PROXY: bool = False

    MAX_IMAGE_BYTES: int = 20 * 1024 * 1024  # 20 MB per image
    SUBMIT_RATE_LIMIT: int = 10  # max job submissions per IP per minute

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
