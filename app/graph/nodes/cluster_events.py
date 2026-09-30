from app.graph.state import RadarState


def cluster_events(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("cluster_events")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}