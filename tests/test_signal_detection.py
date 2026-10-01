from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from app.domain.enums import SourceType
from app.domain.event import Event
from app.domain.source_item import SourceItem
from app.graph.nodes.detect_signals import detect_signals as detect_signals_node
from app.graph.radar_graph import build_radar_graph
from app.infrastructure.llm.signal_detection import (
    SignalCandidate,
    SignalDetectionResponse,
)
from app.services.signal_detection import detect_signals


class FakeLLMProvider:
    def __init__(self, response: SignalDetectionResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> SignalDetectionResponse:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_model": response_model,
            }
        )
        return self.response


def build_event(title: str) -> Event:
    source_item = SourceItem(
        title=title,
        url="https://example.com/event",
        source_name="Example",
        published_at=datetime.now(timezone.utc),
        content=f"Evidence for {title}.",
        source_type=SourceType.MEDIA,
    )
    return Event(title=title, summary=f"Summary for {title}.", source_items=[source_item])


@pytest.mark.asyncio
async def test_empty_events_do_not_invoke_llm() -> None:
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[]))

    assert await detect_signals([], provider) == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_events_become_signal_with_domain_uuid_and_preserved_scores() -> None:
    first_event = build_event("Agents gain autonomy")
    second_event = build_event("Agents gain security controls")
    candidate = SignalCandidate(
        title="Agent infrastructure is becoming an enterprise layer",
        description="Multiple events indicate a shared infrastructure shift.",
        relevance_score=91,
        novelty_score=82,
        confidence_score=76,
        topics=["agents", "architecture"],
        related_event_ids=[first_event.id, second_event.id],
    )
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[candidate]))

    signals = await detect_signals([first_event, second_event], provider)

    assert len(signals) == 1
    assert signals[0].id != first_event.id
    UUID(str(signals[0].id))
    assert signals[0].relevance_score == 91
    assert signals[0].novelty_score == 82
    assert signals[0].confidence_score == 76
    assert signals[0].related_event_ids == [first_event.id, second_event.id]
    assert provider.calls[0]["response_model"] is SignalDetectionResponse


@pytest.mark.asyncio
async def test_unknown_related_event_ids_are_filtered() -> None:
    event = build_event("A real event")
    candidate = SignalCandidate(
        title="A grounded signal",
        description="The real event supports this signal.",
        relevance_score=50,
        novelty_score=50,
        confidence_score=50,
        topics=["software"],
        related_event_ids=[event.id, uuid4()],
    )
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[candidate]))

    signals = await detect_signals([event], provider)

    assert len(signals) == 1
    assert signals[0].related_event_ids == [event.id]


@pytest.mark.asyncio
async def test_signal_with_only_unknown_events_is_discarded() -> None:
    event = build_event("A real event")
    candidate = SignalCandidate(
        title="Unsupported signal",
        description="No supplied event supports this.",
        relevance_score=50,
        novelty_score=50,
        confidence_score=50,
        topics=["unsupported"],
        related_event_ids=[uuid4()],
    )
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[candidate]))

    assert await detect_signals([event], provider) == []


@pytest.mark.asyncio
async def test_zero_signals_from_llm_returns_empty_list() -> None:
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[]))

    assert await detect_signals([build_event("An event")], provider) == []


@pytest.mark.asyncio
async def test_node_returns_signals_and_preserves_execution_trace() -> None:
    event = build_event("A meaningful event")
    candidate = SignalCandidate(
        title="A useful signal",
        description="The event provides enough evidence.",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["business"],
        related_event_ids=[event.id],
    )
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[candidate]))
    state = {
        "run_id": "run-001",
        "source_items": [],
        "events": [event],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["cluster_events"]},
    }

    result = await detect_signals_node(state, provider)

    assert len(result["signals"]) == 1
    assert result["metadata"] == {
        "execution_trace": ["cluster_events", "detect_signals"]
    }


@pytest.mark.asyncio
async def test_workflow_runs_with_injected_fake_provider() -> None:
    provider = FakeLLMProvider(SignalDetectionResponse(signals=[]))
    state = {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    result = await build_radar_graph(provider).ainvoke(state)

    assert result["signals"] == []
    assert result["metadata"]["execution_trace"][-1] == "rank_opportunities"
    assert provider.calls == []