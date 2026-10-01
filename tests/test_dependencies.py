import importlib
from unittest.mock import patch

from app.core.dependencies import build_llm_provider
from app.core.settings import Settings


def test_build_llm_provider_constructs_openai_provider() -> None:
    settings = Settings(OPENAI_API_KEY="test-key", LLM_MODEL="test-model")

    with patch("app.core.dependencies.OpenAILLMProvider") as provider_class:
        provider = build_llm_provider(settings)

    provider_class.assert_called_once_with(settings)
    assert provider is provider_class.return_value


def test_importing_main_does_not_require_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    main_module = importlib.import_module("app.main")

    assert main_module.app.title == "Radar Leyendario IA"