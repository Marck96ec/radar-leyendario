import os

from app.core.settings import Settings, get_settings
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.infrastructure.database.radar_run_repository import SQLiteRadarRunRepository
from app.infrastructure.sources.rss_provider import RSSSourceProvider
from app.infrastructure.sources.config import load_enabled_feeds
from app.services.ports.source import SourceProvider
from app.services.ports.llm import LLMProvider
from app.services.ports.radar_run import RadarRunRepository


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings if settings is not None else get_settings()
    return OpenAILLMProvider(resolved_settings)


def get_llm_provider() -> LLMProvider:
    return build_llm_provider()


def build_source_provider() -> SourceProvider:
    # Feed URLs remain external configuration until they are verified for this deployment.
    return RSSSourceProvider(load_enabled_feeds())


def get_source_provider() -> SourceProvider:
    return build_source_provider()


def get_radar_run_repository() -> RadarRunRepository:
    database_path = os.getenv("RADAR_RUN_DATABASE_PATH", "radar_runs.sqlite3")
    return SQLiteRadarRunRepository(database_path)