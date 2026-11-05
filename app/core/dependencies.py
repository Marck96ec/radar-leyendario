from fastapi import Header, HTTPException, status

from app.core.settings import Settings, get_settings
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.infrastructure.sources.config import load_rss_feeds
from app.infrastructure.sources.rss_provider import RSSSourceProvider
from app.repositories.runs import RunRepository, SQLiteRunRepository
from app.services.ports.source import SourceProvider
from app.services.ports.llm import LLMProvider


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings if settings is not None else get_settings()
    return OpenAILLMProvider(resolved_settings)


def get_llm_provider() -> LLMProvider:
    return build_llm_provider()


def build_source_provider(settings: Settings | None = None) -> SourceProvider:
    resolved_settings = settings if settings is not None else get_settings()
    return RSSSourceProvider(
        load_rss_feeds(resolved_settings.RSS_FEEDS),
        timeout_seconds=resolved_settings.RSS_TIMEOUT_SECONDS,
    )


def get_source_provider() -> SourceProvider:
    return build_source_provider()


def get_run_repository() -> RunRepository:
    return SQLiteRunRepository(get_settings().RUNS_DATABASE_PATH)


def require_radar_access(
    x_radar_api_key: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    configured_key = settings.RADAR_API_KEY.get_secret_value()
    if not configured_key:
        if settings.ENVIRONMENT.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RADAR_API_KEY is required in production",
            )
        return
    if x_radar_api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Radar-API-Key",
        )