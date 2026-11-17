from app.graph.state import RadarState
from app.services.source_content import (
    MIN_SOURCE_CONTENT_CHARS,
    clean_source_text,
    has_sufficient_source_content,
)


def normalize_sources(state: RadarState) -> dict[str, object]:
    normalized_source_items = [
        source_item.model_copy(
            update={
                "content": clean_source_text(source_item.content)
                or source_item.title
            }
        )
        for source_item in state["source_items"]
    ]
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("normalize_sources")
    metadata["execution_trace"] = execution_trace
    enrichment_metadata = metadata.get("content_enrichment", {})
    configured_minimum = (
        enrichment_metadata.get("minimum_content_chars")
        if isinstance(enrichment_metadata, dict)
        else None
    )
    minimum_chars = (
        int(configured_minimum)
        if isinstance(configured_minimum, int) and configured_minimum > 0
        else MIN_SOURCE_CONTENT_CHARS
    )
    sufficient_count = sum(
        has_sufficient_source_content(
            source_item.content, minimum_chars=minimum_chars
        )
        for source_item in normalized_source_items
    )
    metadata["content_quality"] = {
        "sources_with_sufficient_content": sufficient_count,
        "sources_with_insufficient_content": len(normalized_source_items)
        - sufficient_count,
        "minimum_content_chars": minimum_chars,
    }
    quality_metrics = dict(metadata.get("quality_metrics", {}))
    quality_metrics["sources_with_sufficient_content"] = sufficient_count
    metadata["quality_metrics"] = quality_metrics
    return {"source_items": normalized_source_items, "metadata": metadata}