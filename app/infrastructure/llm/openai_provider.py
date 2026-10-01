from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.settings import Settings
from app.services.ports.llm import LLMProvider, T


class OpenAILLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._model = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
        )

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        structured_model = self._model.with_structured_output(response_model)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        result = await structured_model.ainvoke(messages)
        return cast(T, result)
