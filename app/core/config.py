from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    GEMINI_API_KEY: str

    IMAGE_DIR: str = "images"

    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_ENGINE: str = "gemini"
    ANALYSIS_SAMPLES: int = 3
    AI_MAX_CONCURRENT: int = 10

    REDIS_URL: str = "redis://localhost:6379"

    MAX_IMAGE_BYTES: int = 20 * 1024 * 1024  # 20 MB per image
    SUBMIT_RATE_LIMIT: int = 10  # max job submissions per IP per minute

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
