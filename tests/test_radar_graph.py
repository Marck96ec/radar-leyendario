from copy import deepcopy

import pytest

from app.graph.nodes.collect_sources import collect_sources
from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState
from app.domain.source_item import SourceItem
from app.domain.enums import SourceType
from app.services.models.event_clustering import EventClusteringResponse
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
        assert response_model is EventClusteringResponse
        return EventClusteringResponse(clusters=[])


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