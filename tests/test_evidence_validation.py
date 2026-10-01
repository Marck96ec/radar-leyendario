import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from app.domain.enums import EvidenceType, SourceType
from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.graph.nodes.validate_evidence import validate_evidence as validate_evidence_node
from app.graph.radar_graph import build_radar_graph
from app.services.evidence_validation import validate_evidence
from app.services.models.event_clustering import (
    EventClusterCandidate,
    EventClusteringResponse,
)
from app.services.models.evidence_validation import (
    EvidenceCandidate,
    EvidenceValidationResponse,
)
from app.services.models.signal_detection import (
    SignalCandidate,
    SignalDetectionResponse,
)


class FakeLLMProvider:
    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_model": response_model,
            }
        )
        return self.responses[response_model]


def build_source(title: str) -> SourceItem:
    return SourceItem(
        title=title,
        url=f"https://example.test/{title.replace(' ', '-').lower()}",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content=f"Details about {title}.",
        source_type=SourceType.MEDIA,
    )


def build_signal(event: Event) -> Signal:
    return Signal(
        title="A grounded signal",
        description="The event indicates a meaningful change.",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["technology"],
        related_event_ids=[event.id],
    )


def build_state() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["detect_signals"]},
    }


@pytest.mark.asyncio
async def test_empty_signals_do_not_invoke_llm() -> None:
    provider = FakeLLMProvider({EvidenceValidationResponse: EvidenceValidationResponse(evidence=[])})

    assert await validate_evidence([], [], provider) == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_valid_supporting_and_counter_evidence_become_domain_models() -> None:
    source = build_source("Supporting report")
    event = Event(title="An event", summary="Event summary", source_items=[source])
    signal = build_signal(event)
    response = EvidenceValidationResponse(
        evidence=[
            EvidenceCandidate(
                signal_id=signal.id,
                source_item_id=source.id,
                evidence_type=EvidenceType.SUPPORTING,
                explanation="The report describes the change in the signal.",
                confidence=84,
            ),
            EvidenceCandidate(
                signal_id=signal.id,
                source_item_id=source.id,
                evidence_type=EvidenceType.COUNTER,
                explanation="A detail in the report weakens the signal.",
                confidence=41,
            ),
        ]
    )
    provider = FakeLLMProvider({EvidenceValidationResponse: response})

    evidence = await validate_evidence([signal], [event], provider)

    assert [item.evidence_type for item in evidence] == [
        EvidenceType.SUPPORTING,
        EvidenceType.COUNTER,
    ]
    assert evidence[0].confidence == 84
    assert evidence[0].id not in {signal.id, source.id}
    UUID(str(evidence[0].id))


@pytest.mark.asyncio
async def test_invalid_ids_unrelated_sources_and_duplicates_are_discarded() -> None:
    source = build_source("Eligible report")
    unrelated_source = build_source("Unrelated report")
    event = Event(title="Related event", summary="Summary", source_items=[source])
    unrelated_event = Event(
        title="Other event", summary="Other summary", source_items=[unrelated_source]
    )
    signal = build_signal(event)
    candidate = EvidenceCandidate(
        signal_id=signal.id,
        source_item_id=source.id,
        evidence_type=EvidenceType.SUPPORTING,
        explanation="The report supports the signal.",
        confidence=73,
    )
    response = EvidenceValidationResponse(
        evidence=[
            candidate,
            candidate,
            EvidenceCandidate(
                signal_id=uuid4(),
                source_item_id=source.id,
                evidence_type=EvidenceType.SUPPORTING,
                explanation="Unknown signal.",
                confidence=50,
            ),
            EvidenceCandidate(
                signal_id=signal.id,
                source_item_id=uuid4(),
                evidence_type=EvidenceType.SUPPORTING,
                explanation="Unknown source.",
                confidence=50,
            ),
            EvidenceCandidate(
                signal_id=signal.id,
                source_item_id=unrelated_source.id,
                evidence_type=EvidenceType.COUNTER,
                explanation="This source belongs to another event.",
                confidence=50,
            ),
        ]
    )
    provider = FakeLLMProvider({EvidenceValidationResponse: response})

    evidence = await validate_evidence([signal], [event, unrelated_event], provider)

    assert len(evidence) == 1
    assert evidence[0].source_item_id == source.id


@pytest.mark.asyncio
async def test_node_returns_partial_state_metadata_and_trace() -> None:
    source = build_source("Node report")
    event = Event(title="Node event", summary="Summary", source_items=[source])
    signal = build_signal(event)
    provider = FakeLLMProvider(
        {
            EvidenceValidationResponse: EvidenceValidationResponse(
                evidence=[
                    EvidenceCandidate(
                        signal_id=signal.id,
                        source_item_id=source.id,
                        evidence_type=EvidenceType.SUPPORTING,
                        explanation="Specific support.",
                        confidence=66,
                    )
                ]
            )
        }
    )
    state = build_state()
    state["events"] = [event]
    state["signals"] = [signal]

    result = await validate_evidence_node(state, provider)

    assert isinstance(result["evidence"][0], Evidence)
    assert result["metadata"] == {
        "execution_trace": ["detect_signals", "validate_evidence"],
        "evidence_count": 1,
    }


class FakeSourceProvider:
    def __init__(self, source_items: list[SourceItem]) -> None:
        self.source_items = source_items

    async def fetch(self) -> list[SourceItem]:
        return self.source_items


@pytest.mark.asyncio
async def test_workflow_uses_one_offline_provider_for_all_structured_steps() -> None:
    source = build_source("Workflow report")
    event_candidate = EventClusterCandidate(
        title="Workflow event",
        summary="Workflow summary",
        source_item_ids=[source.id],
    )
    class WorkflowFakeLLMProvider(FakeLLMProvider):
        def __init__(self) -> None:
            super().__init__({})

        async def structured_completion(
            self,
            system_prompt: str,
            user_prompt: str,
            response_model: type[BaseModel],
        ) -> BaseModel:
            self.calls.append(
                {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response_model": response_model,
                }
            )
            if response_model is EventClusteringResponse:
                return EventClusteringResponse(clusters=[event_candidate])
            if response_model is SignalDetectionResponse:
                event_id = json.loads(user_prompt.split("Events (JSON):\n", 1)[1])[0]["id"]
                return SignalDetectionResponse(
                    signals=[
                        SignalCandidate(
                            title="Workflow signal",
                            description="Workflow description",
                            relevance_score=80,
                            novelty_score=70,
                            confidence_score=90,
                            topics=["workflow"],
                            related_event_ids=[event_id],
                        )
                    ]
                )
            if response_model is EvidenceValidationResponse:
                payload = json.loads(
                    user_prompt.split("Signals and eligible source items (JSON):\n", 1)[1]
                )
                return EvidenceValidationResponse(
                    evidence=[
                        EvidenceCandidate(
                            signal_id=payload[0]["signal"]["id"],
                            source_item_id=payload[0]["eligible_source_items"][0]["id"],
                            evidence_type=EvidenceType.SUPPORTING,
                            explanation="The workflow source supports the signal.",
                            confidence=88,
                        )
                    ]
                )
            raise AssertionError(f"Unsupported response model: {response_model}")

    provider = WorkflowFakeLLMProvider()

    result = await build_radar_graph(
        llm_provider=provider,
        source_provider=FakeSourceProvider([source]),
    ).ainvoke(build_state())

    assert len(result["evidence"]) == 1
    assert [call["response_model"] for call in provider.calls] == [
        EventClusteringResponse,
        SignalDetectionResponse,
        EvidenceValidationResponse,
    ]