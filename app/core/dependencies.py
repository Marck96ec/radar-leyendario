from app.core.settings import Settings, get_settings
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.infrastructure.sources.rss_provider import RSSSourceProvider
from app.services.ports.source import SourceProvider
from app.services.ports.llm import LLMProvider


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings if settings is not None else get_settings()
    return OpenAILLMProvider(resolved_settings)


def get_llm_provider() -> LLMProvider:
    return build_llm_provider()


def build_source_provider() -> SourceProvider:
    # Feed URLs remain external configuration until they are verified for this deployment.
    return RSSSourceProvider([])


def get_source_provider() -> SourceProvider:
    return build_source_provider()