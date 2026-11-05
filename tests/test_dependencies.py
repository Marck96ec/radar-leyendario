import importlib
from unittest.mock import patch

from app.core.dependencies import build_llm_provider, build_source_provider
from app.core.settings import Settings


def test_build_llm_provider_constructs_openai_provider() -> None:
    settings = Settings(OPENAI_API_KEY="test-key", LLM_MODEL="test-model")

    with patch("app.core.dependencies.OpenAILLMProvider") as provider_class:
        provider = build_llm_provider(settings)

    provider_class.assert_called_once_with(settings)
    assert provider is provider_class.return_value


def test_build_source_provider_wires_volume_limits_from_settings() -> None:
    settings = Settings(
        RSS_FEEDS='[{"name":"Example","url":"https://example.test/feed.xml","source_type":"MEDIA"}]',
        RSS_MAX_ITEMS_PER_FEED=5,
        RSS_MAX_ITEM_AGE_HOURS=24,
        RSS_MAX_TOTAL_ITEMS=20,
    )

    provider = build_source_provider(settings)

    assert provider._max_items_per_feed == 5
    assert provider._max_item_age_hours == 24
    assert provider._max_total_items == 20


def test_importing_main_does_not_require_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    main_module = importlib.import_module("app.main")

    assert main_module.app.title == "Radar Leyendario IA"