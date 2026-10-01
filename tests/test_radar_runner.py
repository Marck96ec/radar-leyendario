from uuid import UUID

import pytest

from app.services.radar_runner import run_radar


EXPECTED_TRACE = [
    "collect_sources",
    "normalize_sources",
    "cluster_events",
    "detect_signals",
    "validate_evidence",
    "generate_opportunities",
    "rank_opportunities",
]


@pytest.mark.asyncio
async def test_run_radar_executes_the_async_workflow() -> None:
    state = await run_radar()

    UUID(state["run_id"])
    assert state["metadata"]["execution_trace"] == EXPECTED_TRACE
    assert state["source_items"] == []
    assert state["events"] == []
    assert state["signals"] == []
    assert state["evidence"] == []
    assert state["opportunities"] == []
    assert state["ranked_opportunities"] == []