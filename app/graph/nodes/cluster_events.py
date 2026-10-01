from app.graph.state import RadarState
from app.services.event_clustering import cluster_events as cluster_events_service
from app.services.ports.llm import LLMProvider


async def cluster_events(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["source_items"] and llm_provider is None:
        raise ValueError("llm_provider is required when source_items are present")

    events = (
        await cluster_events_service(state["source_items"], llm_provider)
        if state["source_items"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("cluster_events")
    metadata["execution_trace"] = execution_trace
    metadata["event_count"] = len(events)
    return {"events": events, "metadata": metadata}


def build_cluster_events_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await cluster_events(state, llm_provider)

    return node