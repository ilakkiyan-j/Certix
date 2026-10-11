from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Certix"
    APP_ENV: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql+psycopg://certix:certix@localhost:5432/certix"

    # Redis URL for background queues
    REDIS_URL: str = "redis://localhost:6379/0"
    QUEUE_NAME: str = "certix_jobs"

    # File Storage Directory
    CERTIFICATE_STORAGE_DIR: Path = Field(default=Path("./storage/generated").resolve())

    @field_validator("CERTIFICATE_STORAGE_DIR", mode="before")
    @classmethod
    def parse_storage_dir(cls, v: str | Path) -> Path:
        p = Path(v)
        return p.resolve()


settings = Settings()
