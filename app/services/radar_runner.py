from uuid import uuid4

from app.graph.radar_graph import build_radar_graph
from app.graph.state import RadarState


def run_radar() -> RadarState:
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

    return build_radar_graph().invoke(initial_state)
