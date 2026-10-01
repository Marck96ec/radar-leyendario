from uuid import uuid4

from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState
from app.services.ports.llm import LLMProvider
from app.services.ports.source import SourceProvider


async def run_radar(
    llm_provider: LLMProvider | None = None,
    source_provider: SourceProvider | None = None,
) -> RadarState:
    initial_state: RadarState = {
        "run_id": str(uuid4()),
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    return await build_radar_graph(llm_provider, source_provider).ainvoke(initial_state)
