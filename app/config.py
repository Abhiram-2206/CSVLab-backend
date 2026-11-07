import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "CSVLab"
    PROJECT_DESCRIPTION: str = (
        "Backend API where learners upload CSVs, get automatic data-quality reports, "
        "and run sandboxed read-only SQL queries with AI-suggested questions."
    )
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite:///./csvlab.db"
    # Read-only database connection URL (optional, defaults to same DB)
    RO_DATABASE_URL: Optional[str] = None

    # JWT Authentication
    SECRET_KEY: str = "csvlab-super-secret-production-key-change-in-env-32bytes-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Storage & Upload Limits
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Query Execution Constraints
    QUERY_TIMEOUT_SECONDS: int = 5
    MAX_QUERY_ROWS: int = 1000

    # AI Integration (Groq)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Rate limiting defaults
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
