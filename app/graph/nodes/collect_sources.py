from app.graph.state import RadarState


def collect_sources(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("collect_sources")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}