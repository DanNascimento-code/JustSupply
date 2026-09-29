from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="JUSTSUPPLY_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://justsupply:justsupply@localhost:5433/justsupply"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    open_food_facts_base_url: str = "https://world.openfoodfacts.org"
    open_food_facts_user_agent: str = (
        "JustSupply/0.1 (https://github.com/DanNascimento-code/JustSupply)"
    )
    open_food_facts_timeout_seconds: float = 8.0
    usda_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JUSTSUPPLY_USDA_API_KEY", "USDA_API_KEY"),
    )
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    usda_timeout_seconds: float = 8.0
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JUSTSUPPLY_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_search_model: str = "gemini-3.5-flash-lite"
    google_grounding_enabled: bool = False
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: Literal[1536] = 1536
    gemini_timeout_seconds: float = 20.0
    tavily_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JUSTSUPPLY_TAVILY_API_KEY", "TAVILY_API_KEY"),
    )
    tavily_base_url: str = "https://api.tavily.com"
    tavily_timeout_seconds: float = 20.0
    wikidata_base_url: str = "https://www.wikidata.org"
    wikidata_timeout_seconds: float = 10.0
    ai_research_ttl_days: int = 7
    catalog_cache_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
