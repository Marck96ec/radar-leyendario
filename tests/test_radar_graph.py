from copy import deepcopy

import pytest

from app.graph.nodes.collect_sources import collect_sources
from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState


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


def test_node_does_not_mutate_received_state() -> None:
    state = build_empty_state()
    original_state = deepcopy(state)

    result = collect_sources(state)

    assert state == original_state
    assert result == {"metadata": {"execution_trace": ["collect_sources"]}}