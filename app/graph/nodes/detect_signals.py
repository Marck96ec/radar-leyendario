from app.graph.state import RadarState


def detect_signals(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("detect_signals")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}