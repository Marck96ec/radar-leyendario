from app.graph.state import RadarState
from app.services.ports.source import SourceProvider


def _trace_metadata(state: RadarState, source_count: int) -> dict[str, object]:
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("collect_sources")
    metadata["execution_trace"] = execution_trace
    metadata["source_count"] = source_count
    return metadata


async def collect_sources(
    state: RadarState, source_provider: SourceProvider | None = None
) -> dict[str, object]:
    if source_provider is None:
        return {
            "source_items": [],
            "metadata": _trace_metadata(state, 0),
        }

    source_items = await source_provider.fetch()
    return {
        "source_items": source_items,
        "metadata": _trace_metadata(state, len(source_items)),
    }


def build_collect_sources_node(source_provider):
    async def node(state):
        return await collect_sources(state, source_provider)

    return node