from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str
    JWT_ALG: str = "HS256"
    JWT_TOKEN_LIFETIME: int = 86400

    DOWNLOAD_DIR: Path = Path("./downloads")
    DOWNLOAD_WORKERS: int = 2
    DOWNLOAD_VERIFY: str = "probe"              # off | probe | full
    DOWNLOAD_MAX_ATTEMPTS: int = 3
    DOWNLOAD_RETRY_DELAY: float = 5.0
    DOWNLOAD_PROGRESS_INTERVAL: float = 1.0
    DOWNLOAD_SOCKET_TIMEOUT: float = 30.0
    DOWNLOAD_EXTRACTOR_RETRIES: int = 5
    DOWNLOAD_FRAGMENT_CONCURRENCY: int = 4

    @field_validator("DOWNLOAD_DIR")
    @classmethod
    def _expand_download_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("DOWNLOAD_WORKERS", "DOWNLOAD_MAX_ATTEMPTS",
                     "DOWNLOAD_EXTRACTOR_RETRIES", "DOWNLOAD_FRAGMENT_CONCURRENCY")
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @field_validator("DOWNLOAD_SOCKET_TIMEOUT", "DOWNLOAD_PROGRESS_INTERVAL")
    @classmethod
    def _validate_positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @field_validator("DOWNLOAD_RETRY_DELAY")
    @classmethod
    def _validate_retry_delay(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be >= 0")
        return value

    @field_validator("DOWNLOAD_VERIFY")
    @classmethod
    def _validate_verify(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ("off", "probe", "full"):
            raise ValueError("DOWNLOAD_VERIFY must be off, probe or full")
        return value


settings = Settings()