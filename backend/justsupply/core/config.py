from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="JUSTSUPPLY_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://justsupply:justsupply@localhost:5433/justsupply"


@lru_cache
def get_settings() -> Settings:
    return Settings()
