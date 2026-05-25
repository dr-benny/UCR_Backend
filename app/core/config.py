import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Google Maps / Street View
    GOOGLE_MAPS_API_KEY: str

    # Google Gemini
    GEMINI_API_KEY: str

    # PostgreSQL
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/architecture"

    # Street View image storage
    IMAGE_DIR: str = "images"

    # Street View defaults
    STREETVIEW_SIZE: str = "640x640"
    STREETVIEW_DEFAULT_FOV: int = 90
    STREETVIEW_DEFAULT_PITCH: int = 0

    # Gemini model (changed to 2.5-flash to bypass the 20-req/day limit of the latest model series)
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # AI Engine selection (swap AI provider here: "gemini", "claude", "gpt4")
    AI_ENGINE: str = "gemini"

    # Self-consistency sampling: number of AI calls per image then aggregate.
    # 1 = disabled (fast, original behaviour). 3 = recommended.
    ANALYSIS_SAMPLES: int = 3

    # Hard cap on concurrent AI API calls across the entire app.
    # Prevents rate-limit errors when batch × sampling multiply together.
    # e.g. batch=5 images × samples=3 = 15 potential calls → capped here.
    AI_MAX_CONCURRENT: int = 10

    # Redis / ARQ
    REDIS_URL: str = "redis://localhost:6379"

    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-southeast-1"
    S3_BUCKET_NAME: str = ""



    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
