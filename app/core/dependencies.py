from app.core.settings import Settings, get_settings
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.services.ports.llm import LLMProvider


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings if settings is not None else get_settings()
    return OpenAILLMProvider(resolved_settings)


def get_llm_provider() -> LLMProvider:
    return build_llm_provider()