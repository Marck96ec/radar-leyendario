import logging
from time import perf_counter
from uuid import uuid4

from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState
from app.services.ports.llm import LLMProvider
from app.services.ports.source import SourceProvider


logger = logging.getLogger(__name__)


async def run_radar(
    llm_provider: LLMProvider | None = None,
    source_provider: SourceProvider | None = None,
    run_id: str | None = None,
) -> RadarState:
    started = perf_counter()
    initial_state: RadarState = {
        "run_id": run_id or str(uuid4()),
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    state = await build_radar_graph(llm_provider, source_provider).ainvoke(initial_state)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    metadata = dict(state["metadata"])
    metadata["duration_ms"] = duration_ms
    metadata["event_count"] = len(state["events"])
    metadata["signal_count"] = len(state["signals"])
    metadata["evidence_count"] = len(state["evidence"])
    metadata["opportunity_count"] = len(state["opportunities"])
    metadata["ranked_opportunity_count"] = len(state["ranked_opportunities"])
    state["metadata"] = metadata
    logger.info(
        "Radar run completed",
        extra={
            "run_id": state["run_id"],
            "duration_ms": duration_ms,
            "source_count": len(state["source_items"]),
            "event_count": len(state["events"]),
            "signal_count": len(state["signals"]),
            "opportunity_count": len(state["opportunities"]),
        },
    )
    return state
