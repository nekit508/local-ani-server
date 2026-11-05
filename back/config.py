from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str
    JWT_ALG: str = "HS256"
    JWT_TOKEN_LIFETIME: int = 86400
    DOWNLOAD_DIR: str = "."
    FRAGMENTS_PARALLEL: int = 4

    BACK_HOST: str
    BACK_PORT: int

    DB_FILE: str = ".db"

    DOWNLOADER_SOCKET_TIMEOUT: int = 10
    DOWNLOADER_CONCURRENT_FRAGMENT_DOWNLOADS: int = 2
    DOWNLOADER_OUTPUT_FORMAT: str = "mp4"

    EXECUTOR_WORKERS_NUM: int = 4

try:
    # noinspection PyArgumentList
    settings = Settings()
except ValidationError as e:
    raise RuntimeError("Error while validating .env file:", e)