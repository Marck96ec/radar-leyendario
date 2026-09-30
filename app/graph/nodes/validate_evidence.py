from app.graph.state import RadarState


def validate_evidence(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("validate_evidence")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}