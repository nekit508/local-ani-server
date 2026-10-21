from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str
    JWT_ALG: str = "HS256"
    JWT_TOKEN_LIFETIME: int = 86400


settings = Settings()