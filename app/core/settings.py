from pydantic import SecretStr
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENAI_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "gpt-4o-mini"
    RSS_FEEDS: str = ""
    RSS_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=120)
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
