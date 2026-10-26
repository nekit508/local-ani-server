from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str
    JWT_ALG: str = "HS256"
    JWT_TOKEN_LIFETIME: int = 86400
    DOWNLOAD_DIR: str = "."
    WORKERS_NUM: int = 4
    FRAGMENTS_PARALLEL: int = 4

    BACK_HOST: str
    BACK_PORT: int


try:
    # noinspection PyArgumentList
    settings = Settings()
except ValidationError as e:
    raise RuntimeError("Error while validating .env file:", e)