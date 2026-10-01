import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.domain.enums import EvidenceType, OpportunityCategory, SourceType
from app.domain.evidence import Evidence
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.graph.nodes.generate_opportunities import generate_opportunities as generate_opportunities_node
from app.services.models.opportunity_generation import (
    OpportunityCandidate,
    OpportunityGenerationResponse,
)
from app.services.opportunity_generation import generate_opportunities


class FakeLLMProvider:
    def __init__(self, response: OpportunityGenerationResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> OpportunityGenerationResponse:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_model": response_model,
            }
        )
        return self.response


def build_source() -> SourceItem:
    return SourceItem(
        title="A relevant report",
        url="https://example.test/report",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="The report describes a concrete change.",
        source_type=SourceType.MEDIA,
    )


def build_signal() -> Signal:
    return Signal(
        title="A grounded shift",
        description="A concrete shift is becoming visible.",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["technology"],
        related_event_ids=[uuid4()],
    )


def build_evidence(signal: Signal, source: SourceItem) -> Evidence:
    return Evidence(
        signal_id=signal.id,
        source_item_id=source.id,
        evidence_type=EvidenceType.SUPPORTING,
        explanation="The report directly describes the shift.",
        confidence=86,
    )


def build_candidate(signal_id: UUID, category: OpportunityCategory) -> OpportunityCandidate:
    return OpportunityCandidate(
        signal_id=signal_id,
        title="Explore a useful action",
        description="Build an action based on the supplied signal and evidence.",
        why_now="The supplied report describes the change now.",
        category=category,
        impact_score=80,
        timing_score=75,
        novelty_score=70,
        content_potential=65,
        business_potential=60,
        evidence_confidence=86,
    )


@pytest.mark.asyncio
async def test_empty_signals_return_without_calling_llm() -> None:
    provider = FakeLLMProvider(OpportunityGenerationResponse(opportunities=[]))

    assert await generate_opportunities([], [], [], provider) == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_signal_without_evidence_returns_without_calling_llm() -> None:
    signal = build_signal()
    provider = FakeLLMProvider(OpportunityGenerationResponse(opportunities=[]))

    assert await generate_opportunities([signal], [], [], provider) == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_valid_candidate_becomes_traceable_domain_opportunity() -> None:
    signal = build_signal()
    source = build_source()
    provider = FakeLLMProvider(
        OpportunityGenerationResponse(
            opportunities=[build_candidate(signal.id, OpportunityCategory.CONTENT)]
        )
    )

    opportunities = await generate_opportunities(
        [signal], [build_evidence(signal, source)], [source], provider
    )

    assert len(opportunities) == 1
    assert opportunities[0].id != signal.id
    assert isinstance(opportunities[0].id, UUID)
    assert opportunities[0].signal_id == signal.id
    assert opportunities[0].final_score is None
    assert opportunities[0].impact_score == 80
    assert provider.calls[0]["response_model"] is OpportunityGenerationResponse


@pytest.mark.asyncio
async def test_unknown_signal_ids_are_discarded_and_grounding_is_signal_local() -> None:
    signal = build_signal()
    source = build_source()
    provider = FakeLLMProvider(
        OpportunityGenerationResponse(
            opportunities=[
                build_candidate(uuid4(), OpportunityCategory.BUSINESS),
                build_candidate(signal.id, OpportunityCategory.BUSINESS),
            ]
        )
    )

    opportunities = await generate_opportunities(
        [signal], [build_evidence(signal, source)], [source], provider
    )
    payload = json.loads(provider.calls[0]["user_prompt"].split("(JSON):\n", 1)[1])

    assert len(opportunities) == 1
    assert payload["signal"]["id"] == str(signal.id)
    assert payload["evidence"][0]["source_item"]["id"] == str(source.id)


def test_response_rejects_more_than_three_opportunities() -> None:
    signal = build_signal()
    candidates = [build_candidate(signal.id, OpportunityCategory.CONTENT) for _ in range(5)]

    with pytest.raises(ValidationError):
        OpportunityGenerationResponse(opportunities=candidates)


@pytest.mark.parametrize("category", list(OpportunityCategory))
def test_all_opportunity_categories_are_accepted(category: OpportunityCategory) -> None:
    candidate = build_candidate(uuid4(), category)

    assert candidate.category is category


def test_candidate_rejects_scores_outside_range() -> None:
    candidate_data = build_candidate(
        uuid4(), OpportunityCategory.CONTENT
    ).model_dump()
    candidate_data["evidence_confidence"] = 101

    with pytest.raises(ValidationError):
        OpportunityCandidate.model_validate(candidate_data)


@pytest.mark.asyncio
async def test_node_returns_partial_state_metadata_and_trace() -> None:
    signal = build_signal()
    source = build_source()
    provider = FakeLLMProvider(
        OpportunityGenerationResponse(
            opportunities=[build_candidate(signal.id, OpportunityCategory.ARCHITECTURE)]
        )
    )
    state = {
        "run_id": "run-001",
        "source_items": [source],
        "events": [],
        "signals": [signal],
        "evidence": [build_evidence(signal, source)],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["validate_evidence"]},
    }

    result = await generate_opportunities_node(state, provider)

    assert len(result["opportunities"]) == 1
    assert result["metadata"] == {
        "execution_trace": ["validate_evidence", "generate_opportunities"],
        "opportunity_count": 1,
    }
