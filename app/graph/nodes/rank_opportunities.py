from app.graph.state import RadarState
from app.services.opportunity_ranking import (
    rank_opportunities as rank_opportunities_service,
)


def rank_opportunities(state: RadarState) -> dict[str, object]:
    ranked = rank_opportunities_service(state["opportunities"])
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("rank_opportunities")
    metadata["execution_trace"] = execution_trace
    metadata["ranked_opportunity_count"] = len(ranked)
    return {"ranked_opportunities": ranked, "metadata": metadata}