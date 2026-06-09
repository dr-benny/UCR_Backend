from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    ANTHROPIC_API_KEY: str | None = None

    IMAGE_DIR: str = "images"
    PROMPT_DIR: str = "prompt_store"  # durable on-disk store for custom prompt library

    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_ENGINE: str = "gemini"
    ANALYSIS_SAMPLES: int = 3
    MAX_ANALYSIS_SAMPLES: int = 5  # upper bound a caller may request per image (C1)
    MAX_JOB_API_CALLS: int = 1000  # reject a job whose images × samples exceeds this (C1)
    AI_MAX_CONCURRENT: int = 10
    AI_CALL_TIMEOUT: int = 120  # seconds per AI API call before it's aborted + retried (R3)

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
    MAX_JOB_TOTAL_BYTES: int = 1024 * 1024 * 1024  # 1 GB total across one job's images (D2)
    SUBMIT_RATE_LIMIT: int = 10  # max job submissions per IP per minute

    MAX_PROMPT_CHARS: int = 20000  # upper bound on a stored custom prompt's length

    # WebSocket: send a heartbeat + re-check job state every N seconds so a
    # client never blocks forever on a stalled job (R2).
    WS_HEARTBEAT_INTERVAL: int = 30
    # A pending/processing job whose heartbeat is older than this is considered
    # stalled (worker crashed / never picked up) and marked failed (R1).
    STUCK_JOB_TIMEOUT: int = 600
    STUCK_JOB_REAPER_INTERVAL: int = 60  # how often the reaper scans

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
