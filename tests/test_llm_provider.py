from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import BaseModel, SecretStr

from app.core.settings import Settings
from app.infrastructure.llm.openai_provider import OpenAILLMProvider


class ExampleResponse(BaseModel):
    answer: str
    confidence: float


def test_settings_accepts_openai_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    settings = Settings()

    assert isinstance(settings.OPENAI_API_KEY, SecretStr)
    assert settings.OPENAI_API_KEY.get_secret_value() == "test-key"
    assert settings.LLM_MODEL == "test-model"


def test_settings_repr_does_not_expose_openai_api_key() -> None:
    secret = "test-key-that-must-stay-secret"
    settings = Settings(OPENAI_API_KEY=secret, LLM_MODEL="test-model")

    assert secret not in repr(settings)


def test_provider_uses_configured_model() -> None:
    settings = Settings(OPENAI_API_KEY="test-key", LLM_MODEL="configured-model")

    with patch("app.infrastructure.llm.openai_provider.ChatOpenAI") as chat_openai:
        OpenAILLMProvider(settings)

    chat_openai.assert_called_once_with(
        model="configured-model",
        api_key="test-key",
    )


@pytest.mark.asyncio
async def test_structured_completion_uses_prompts_and_response_model() -> None:
    settings = Settings(OPENAI_API_KEY="test-key", LLM_MODEL="test-model")
    expected = ExampleResponse(answer="ready", confidence=0.95)
    structured_model = Mock()
    structured_model.ainvoke = AsyncMock(return_value=expected)

    with patch("app.infrastructure.llm.openai_provider.ChatOpenAI") as chat_openai:
        chat_model = chat_openai.return_value
        chat_model.with_structured_output.return_value = structured_model
        provider = OpenAILLMProvider(settings)

        result = await provider.structured_completion(
            system_prompt="You are concise.",
            user_prompt="Say ready.",
            response_model=ExampleResponse,
        )

    assert result is expected
    chat_model.with_structured_output.assert_called_once_with(ExampleResponse)
    messages = structured_model.ainvoke.await_args.args[0]
    assert [message.content for message in messages] == [
        "You are concise.",
        "Say ready.",
    ]
    assert messages[0].type == "system"
    assert messages[1].type == "human"


@pytest.mark.asyncio
async def test_provider_satisfies_llm_port_without_network() -> None:
    settings = Settings(OPENAI_API_KEY="test-key", LLM_MODEL="test-model")
    expected = ExampleResponse(answer="ok", confidence=1.0)
    structured_model = Mock()
    structured_model.ainvoke = AsyncMock(return_value=expected)

    with patch("app.infrastructure.llm.openai_provider.ChatOpenAI") as chat_openai:
        chat_openai.return_value.with_structured_output.return_value = structured_model
        provider = OpenAILLMProvider(settings)
        result = await provider.structured_completion("system", "user", ExampleResponse)

    assert isinstance(result, ExampleResponse)
    assert result == expected
