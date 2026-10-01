import json

from app.domain.event import Event
from app.domain.source_item import SourceItem
from app.services.models.event_clustering import EventClusteringResponse
from app.services.ports.llm import LLMProvider
from app.services.prompts.event_clustering import (
    SYSTEM_PROMPT,
    build_user_prompt,
)


def _serialize_source_items(source_items: list[SourceItem]) -> str:
    return json.dumps(
        [
            {
                "id": str(source_item.id),
                "title": source_item.title,
                "source_name": source_item.source_name,
                "published_at": source_item.published_at.isoformat(),
                "content": source_item.content,
            }
            for source_item in source_items
        ],
        ensure_ascii=True,
        indent=2,
    )


async def cluster_events(
    source_items: list[SourceItem],
    llm_provider: LLMProvider,
) -> list[Event]:
    if not source_items:
        return []

    response = await llm_provider.structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(_serialize_source_items(source_items)),
        response_model=EventClusteringResponse,
    )
    source_items_by_id = {source_item.id: source_item for source_item in source_items}
    assigned_ids = set()
    events: list[Event] = []

    for candidate in response.clusters:
        valid_ids = []
        for source_item_id in candidate.source_item_ids:
            if (
                source_item_id in source_items_by_id
                and source_item_id not in assigned_ids
                and source_item_id not in valid_ids
            ):
                valid_ids.append(source_item_id)
        if not valid_ids:
            continue

        assigned_ids.update(valid_ids)
        events.append(
            Event(
                title=candidate.title,
                summary=candidate.summary,
                source_items=[source_items_by_id[source_item_id] for source_item_id in valid_ids],
            )
        )

    for source_item in source_items:
        if source_item.id not in assigned_ids:
            events.append(
                Event(
                    title=source_item.title,
                    summary=source_item.content,
                    source_items=[source_item],
                )
            )

    return events