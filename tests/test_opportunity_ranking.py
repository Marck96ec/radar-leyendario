import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from app.domain.enums import EvidenceType, OpportunityCategory, SourceType
from app.domain.opportunity import Opportunity
from app.domain.source_item import SourceItem
from app.graph.nodes.rank_opportunities import rank_opportunities as rank_node
from app.graph.radar_graph import build_radar_graph
from app.services.models.event_clustering import (
    EventClusterCandidate,
    EventClusteringResponse,
)
from app.services.models.evidence_validation import (
    EvidenceCandidate,
    EvidenceValidationResponse,
)
from app.services.models.opportunity_generation import (
    OpportunityCandidate,
    OpportunityGenerationResponse,
)
from app.services.models.signal_detection import SignalCandidate, SignalDetectionResponse
from app.services.opportunity_ranking import rank_opportunities


def build_opportunity(title: str, score: float = 50) -> Opportunity:
    return Opportunity(
        title=title,
        signal_id=uuid4(),
        description="A useful action based on a signal.",
        why_now="The signal is timely.",
        category=OpportunityCategory.CONTENT,
        impact_score=score,
        timing_score=score,
        novelty_score=score,
        content_potential=score,
        business_potential=score,
        evidence_confidence=score,
    )


def test_empty_opportunities_return_empty() -> None:
    assert rank_opportunities([]) == []


def test_formula_is_exact_and_score_is_rounded() -> None:
    opportunity = build_opportunity("Known score").model_copy(
        update={
            "impact_score": 80,
            "timing_score": 70,
            "novelty_score": 60,
            "content_potential": 50,
            "business_potential": 40,
            "evidence_confidence": 30,
        }
    )

    assert rank_opportunities([opportunity])[0].final_score == 60.5


@pytest.mark.parametrize("score", [0, 100])
def test_uniform_scores_preserve_their_value(score: float) -> None:
    assert rank_opportunities([build_opportunity("Uniform", score)])[0].final_score == score


def test_ranking_descends_and_is_limited_to_three() -> None:
    opportunities = [
        build_opportunity("Low", 10),
        build_opportunity("High", 90),
        build_opportunity("Medium", 50),
        build_opportunity("Extra", 80),
    ]

    assert [item.title for item in rank_opportunities(opportunities)] == [
        "High",
        "Extra",
        "Medium",
    ]


def test_equal_scores_preserve_input_order() -> None:
    opportunities = [build_opportunity("First"), build_opportunity("Second")]

    assert [item.title for item in rank_opportunities(opportunities)] == [
        "First",
        "Second",
    ]


def test_original_opportunity_is_not_mutated_and_ranked_copy_preserves_data() -> None:
    opportunity = build_opportunity("Original")
    original = opportunity.model_copy(deep=True)

    ranked = rank_opportunities([opportunity])

    assert opportunity == original
    assert opportunity.final_score is None
    assert ranked[0] is not opportunity
    assert ranked[0].final_score is not None
    assert ranked[0].model_dump(exclude={"final_score"}) == opportunity.model_dump(
        exclude={"final_score"}
    )


def test_node_returns_partial_state_with_count_and_trace() -> None:
    opportunity = build_opportunity("Node opportunity", 80)
    state: dict[str, Any] = {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [opportunity],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["generate_opportunities"]},
    }

    result = rank_node(state)

    assert result["ranked_opportunities"][0].id == opportunity.id
    assert result["ranked_opportunities"][0].signal_id == opportunity.signal_id
    assert result["ranked_opportunities"][0].title == opportunity.title
    assert result["ranked_opportunities"][0].category == opportunity.category
    assert result["metadata"] == {
        "execution_trace": ["generate_opportunities", "rank_opportunities"],
        "ranked_opportunity_count": 1,
    }
    assert opportunity.final_score is None


class FakeSourceProvider:
    def __init__(self, source_items: list[SourceItem]) -> None:
        self.source_items = source_items

    async def fetch(self) -> list[SourceItem]:
        return self.source_items


class OfflineLLMProvider:
    def __init__(self) -> None:
        self.calls: list[type[BaseModel]] = []

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.calls.append(response_model)
        payload = json.loads(user_prompt.split("(JSON):\n", 1)[1])

        if response_model is EventClusteringResponse:
            return EventClusteringResponse(
                clusters=[
                    EventClusterCandidate(
                        title="An event",
                        summary="A concrete event.",
                        source_item_ids=[UUID(payload[0]["id"])],
                    )
                ]
            )
        if response_model is SignalDetectionResponse:
            return SignalDetectionResponse(
                signals=[
                    SignalCandidate(
                        title="A signal",
                        description="A concrete signal.",
                        relevance_score=80,
                        novelty_score=70,
                        confidence_score=90,
                        topics=["technology"],
                        related_event_ids=[UUID(payload[0]["id"])],
                    )
                ]
            )
        if response_model is EvidenceValidationResponse:
            return EvidenceValidationResponse(
                evidence=[
                    EvidenceCandidate(
                        signal_id=UUID(payload[0]["signal"]["id"]),
                        source_item_id=UUID(payload[0]["eligible_source_items"][0]["id"]),
                        evidence_type=EvidenceType.SUPPORTING,
                        explanation="The report supports the signal.",
                        confidence=85,
                    )
                ]
            )
        if response_model is OpportunityGenerationResponse:
            return OpportunityGenerationResponse(
                opportunities=[
                    OpportunityCandidate(
                        signal_id=UUID(payload["signal"]["id"]),
                        title="Act on the signal",
                        description="A useful action.",
                        why_now="The report is current.",
                        category=OpportunityCategory.CONTENT,
                        impact_score=80,
                        timing_score=70,
                        novelty_score=60,
                        content_potential=50,
                        business_potential=40,
                        evidence_confidence=85,
                    )
                ]
            )
        raise AssertionError(f"Unexpected response model: {response_model}")


@pytest.mark.asyncio
async def test_offline_workflow_ranks_without_an_additional_llm_call() -> None:
    source = SourceItem(
        title="A source",
        url="https://example.test/source",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="A concrete report.",
        source_type=SourceType.MEDIA,
    )
    llm = OfflineLLMProvider()
    initial_state = {
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

    result = await build_radar_graph(
        llm_provider=llm,
        source_provider=FakeSourceProvider([source]),
    ).ainvoke(initial_state)

    assert result["opportunities"][0].final_score is None
    assert result["ranked_opportunities"][0].final_score == 66.0
    assert len(llm.calls) == 4
    assert result["metadata"]["ranked_opportunity_count"] == 1
    assert result["metadata"]["execution_trace"] == [
        "collect_sources",
        "normalize_sources",
        "cluster_events",
        "detect_signals",
        "validate_evidence",
        "generate_opportunities",
        "rank_opportunities",
    ]