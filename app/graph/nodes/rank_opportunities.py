from app.graph.state import RadarState


def rank_opportunities(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("rank_opportunities")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}