from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    GOOGLE_MAPS_API_KEY: str
    GEMINI_API_KEY: str

    IMAGE_DIR: str = "images"

    STREETVIEW_SIZE: str = "640x640"
    STREETVIEW_DEFAULT_FOV: int = 90
    STREETVIEW_DEFAULT_PITCH: int = 0

    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_ENGINE: str = "gemini"
    ANALYSIS_SAMPLES: int = 3
    AI_MAX_CONCURRENT: int = 10

    REDIS_URL: str = "redis://localhost:6379"

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
