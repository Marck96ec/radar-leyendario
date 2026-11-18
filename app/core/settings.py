from pydantic import SecretStr
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENAI_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "gpt-4o-mini"
    RSS_FEEDS: str = ""
    RSS_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=120)
    RSS_MAX_ITEMS_PER_FEED: int = Field(default=10, gt=0)
    RSS_MAX_ITEM_AGE_HOURS: float = Field(default=72.0, gt=0)
    RSS_MAX_TOTAL_ITEMS: int = Field(default=50, gt=0)
    RSS_ENRICH_OFFICIAL_CONTENT: bool = True
    RSS_ENRICHMENT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=120)
    RSS_ENRICHMENT_MAX_BYTES: int = Field(default=1_000_000, gt=0)
    RSS_ENRICHMENT_CONCURRENCY: int = Field(default=4, gt=0)
    RSS_ENRICHMENT_MAX_REDIRECTS: int = Field(default=3, ge=0)
    RSS_MIN_CONTENT_CHARS: int = Field(default=400, gt=0)
    RUNS_DATABASE_PATH: str = "./data/radar_runs.sqlite3"
    RADAR_API_KEY: SecretStr = SecretStr("")
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
