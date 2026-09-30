from app.graph.state import RadarState


def normalize_sources(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("normalize_sources")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}