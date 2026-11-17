from copy import deepcopy
import json

import pytest

from app.graph.nodes.collect_sources import collect_sources
from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState
from app.domain.source_item import SourceItem
from app.domain.enums import SourceType
from app.services.models.event_clustering import EventClusteringResponse
from app.services.models.evidence_validation import EvidenceValidationResponse
from app.services.models.signal_detection import SignalDetectionResponse
from app.services.models.signal_detection import SignalCandidate
from app.services.models.event_clustering import EventClusterCandidate
from datetime import datetime, timezone


EXPECTED_TRACE = [
    "collect_sources",
    "normalize_sources",
    "cluster_events",
    "detect_signals",
    "validate_evidence",
    "generate_opportunities",
    "rank_opportunities",
]


def build_empty_state(run_id: str = "run-001") -> RadarState:
    return {
        "run_id": run_id,
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_build_radar_graph_produces_an_invocable_graph() -> None:
    graph = build_radar_graph()

    assert await graph.ainvoke(build_empty_state()) is not None


@pytest.mark.asyncio
async def test_empty_state_traverses_the_complete_placeholder_workflow() -> None:
    state = build_empty_state("run-002")

    result = await build_radar_graph().ainvoke(state)

    assert result["run_id"] == "run-002"
    assert result["metadata"]["execution_trace"] == EXPECTED_TRACE
    assert result["source_items"] == []
    assert result["events"] == []
    assert result["signals"] == []
    assert result["evidence"] == []
    assert result["opportunities"] == []
    assert result["ranked_opportunities"] == []


@pytest.mark.asyncio
async def test_node_does_not_mutate_received_state() -> None:
    state = build_empty_state()
    original_state = deepcopy(state)

    result = await collect_sources(state)

    assert state == original_state
    assert result == {
        "source_items": [],
        "metadata": {"execution_trace": ["collect_sources"], "source_count": 0},
    }


class FakeSourceProvider:
    def __init__(self, source_items: list[SourceItem]) -> None:
        self.source_items = source_items

    async def fetch(self) -> list[SourceItem]:
        return self.source_items


class FakeLLMProvider:
    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[object],
    ) -> object:
        if response_model is EventClusteringResponse:
            return EventClusteringResponse(clusters=[])
        if response_model is SignalDetectionResponse:
            return SignalDetectionResponse(signals=[])
        raise AssertionError(f"Unsupported response model: {response_model}")


@pytest.mark.asyncio
async def test_injected_source_provider_returns_partial_state_and_source_count() -> None:
    source_item = SourceItem(
        title="A publication",
        url="https://example.test/publication",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="Content",
        source_type=SourceType.MEDIA,
    )
    state = build_empty_state()

    result = await build_radar_graph(
        llm_provider=FakeLLMProvider(),
        source_provider=FakeSourceProvider([source_item]),
    ).ainvoke(state)

    assert result["source_items"] == [source_item]
    assert result["metadata"]["source_count"] == 1
    assert result["metadata"]["execution_trace"] == EXPECTED_TRACE


class EmptyEvidenceIntegrationLLM:
    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[object],
    ) -> object:
        if response_model is EventClusteringResponse:
            payload = json.loads(user_prompt.split("Source items (JSON):\n", 1)[1])
            return EventClusteringResponse(
                clusters=[
                    EventClusterCandidate(
                        title="Agents add audit controls",
                        summary="Agents add audit controls.",
                        source_item_ids=[payload[0]["id"]],
                    )
                ]
            )
        if response_model is SignalDetectionResponse:
            payload = json.loads(user_prompt.split("Events (JSON):\n", 1)[1])
            return SignalDetectionResponse(
                signals=[
                    SignalCandidate(
                        title="Agents add audit controls",
                        description="The event reports a concrete control change.",
                        relevance_score=80,
                        novelty_score=70,
                        confidence_score=90,
                        topics=["agents"],
                        related_event_ids=[payload[0]["id"]],
                    )
                ]
            )
        if response_model is EvidenceValidationResponse:
            return EvidenceValidationResponse(evidence=[])
        raise AssertionError(f"Unsupported response model: {response_model}")


@pytest.mark.asyncio
async def test_graph_normalizes_html_and_preserves_empty_evidence_diagnostic() -> None:
    source_item = SourceItem(
        title="Official controls update",
        url="https://example.test/controls",
        source_name="Official",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="<p>Agents add audit controls.</p><script>ignore()</script>",
        source_type=SourceType.OFFICIAL,
    )

    result = await build_radar_graph(
        llm_provider=EmptyEvidenceIntegrationLLM(),
        source_provider=FakeSourceProvider([source_item]),
    ).ainvoke(build_empty_state("run-html"))

    assert result["source_items"][0].content == "Agents add audit controls."
    assert result["evidence"] == []
    assert result["opportunities"] == []
    assert "No se aceptaron evidencias" in result["metadata"]["evidence_warning"]
    assert result["metadata"]["quality_metrics"]["evidence_proposed"] == 0