from app.graph.state import RadarState


def generate_opportunities(state: RadarState) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("generate_opportunities")
    metadata["execution_trace"] = execution_trace
    return {"metadata": metadata}