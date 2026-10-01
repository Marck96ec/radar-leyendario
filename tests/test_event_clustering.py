from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from app.domain.enums import SourceType
from app.domain.source_item import SourceItem
from app.graph.radar_graph import build_radar_graph
from app.graph.nodes.cluster_events import cluster_events as cluster_events_node
from app.services.event_clustering import cluster_events
from app.services.models.event_clustering import (
    EventClusterCandidate,
    EventClusteringResponse,
)
from app.services.models.signal_detection import SignalDetectionResponse


class FakeLLMProvider:
    def __init__(self, clustering_response: EventClusteringResponse) -> None:
        self.clustering_response = clustering_response
        self.calls: list[dict[str, Any]] = []

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_model": response_model,
            }
        )
        if response_model is EventClusteringResponse:
            return self.clustering_response
        if response_model is SignalDetectionResponse:
            return SignalDetectionResponse(signals=[])
        raise AssertionError(f"Unsupported response model: {response_model}")


class FakeSourceProvider:
    def __init__(self, source_items: list[SourceItem]) -> None:
        self.source_items = source_items

    async def fetch(self) -> list[SourceItem]:
        return self.source_items


def build_source_item(title: str) -> SourceItem:
    return SourceItem(
        title=title,
        url=f"https://example.test/{uuid4()}",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content=f"Details about {title}.",
        source_type=SourceType.MEDIA,
    )


@pytest.mark.asyncio
async def test_empty_source_items_do_not_invoke_llm() -> None:
    provider = FakeLLMProvider(EventClusteringResponse(clusters=[]))

    assert await cluster_events([], provider) == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_same_fact_becomes_one_event_with_all_sources() -> None:
    source_items = [build_source_item(f"Launch report {index}") for index in range(3)]
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="Company X launches Agent Platform",
                    summary="Company X announced its new agent platform.",
                    source_item_ids=[source_item.id for source_item in source_items],
                )
            ]
        )
    )

    events = await cluster_events(source_items, provider)

    assert len(events) == 1
    assert events[0].source_items == source_items
    assert UUID(str(events[0].id))
    assert events[0].title == "Company X launches Agent Platform"
    assert events[0].summary == "Company X announced its new agent platform."
    assert provider.calls[0]["response_model"] is EventClusteringResponse


@pytest.mark.asyncio
async def test_distinct_clusters_keep_each_source_item_in_its_own_event() -> None:
    first = build_source_item("First event")
    second = build_source_item("Second event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="First",
                    summary="First summary",
                    source_item_ids=[first.id],
                ),
                EventClusterCandidate(
                    title="Second",
                    summary="Second summary",
                    source_item_ids=[second.id],
                ),
            ]
        )
    )

    events = await cluster_events([first, second], provider)

    assert len(events) == 2
    assert [event.source_items for event in events] == [[first], [second]]


@pytest.mark.asyncio
async def test_omitted_source_item_becomes_singleton_event() -> None:
    first = build_source_item("First event")
    second = build_source_item("Second event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="First",
                    summary="First summary",
                    source_item_ids=[first.id],
                )
            ]
        )
    )

    events = await cluster_events([first, second], provider)

    assert len(events) == 2
    assert events[1].title == second.title
    assert events[1].summary == second.content
    assert events[1].source_items == [second]


@pytest.mark.asyncio
async def test_each_source_item_appears_exactly_once_in_resulting_events() -> None:
    first = build_source_item("First event")
    second = build_source_item("Second event")
    third = build_source_item("Third event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="First and second",
                    summary="First and second summary",
                    source_item_ids=[first.id, second.id],
                )
            ]
        )
    )

    events = await cluster_events([first, second, third], provider)

    flattened_source_items = [
        source_item for event in events for source_item in event.source_items
    ]
    assert flattened_source_items == [first, second, third]
    assert len({source_item.id for source_item in flattened_source_items}) == 3


@pytest.mark.asyncio
async def test_invalid_ids_are_filtered_and_unknown_only_cluster_is_discarded() -> None:
    source_item = build_source_item("A real event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="Unknown",
                    summary="Unknown",
                    source_item_ids=[uuid4()],
                ),
                EventClusterCandidate(
                    title="Real event",
                    summary="Real summary",
                    source_item_ids=[uuid4(), source_item.id],
                ),
            ]
        )
    )

    events = await cluster_events([source_item], provider)

    assert len(events) == 1
    assert events[0].source_items == [source_item]


@pytest.mark.asyncio
async def test_repeated_source_item_is_assigned_to_first_cluster() -> None:
    first = build_source_item("First event")
    second = build_source_item("Second event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="First",
                    summary="First summary",
                    source_item_ids=[first.id, second.id],
                ),
                EventClusterCandidate(
                    title="Second",
                    summary="Second summary",
                    source_item_ids=[second.id],
                ),
            ]
        )
    )

    events = await cluster_events([first, second], provider)

    assert len(events) == 1
    assert events[0].source_items == [first, second]


@pytest.mark.asyncio
async def test_node_returns_events_count_and_execution_trace() -> None:
    source_item = build_source_item("A meaningful event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="Event",
                    summary="Summary",
                    source_item_ids=[source_item.id],
                )
            ]
        )
    )
    state = {
        "run_id": "run-001",
        "source_items": [source_item],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["normalize_sources"]},
    }

    result = await cluster_events_node(state, provider)

    assert len(result["events"]) == 1
    assert result["metadata"] == {
        "execution_trace": ["normalize_sources", "cluster_events"],
        "event_count": 1,
    }


@pytest.mark.asyncio
async def test_workflow_shares_fake_provider_between_clustering_and_detection() -> None:
    source_item = build_source_item("A workflow event")
    provider = FakeLLMProvider(
        EventClusteringResponse(
            clusters=[
                EventClusterCandidate(
                    title="Workflow event",
                    summary="Workflow summary",
                    source_item_ids=[source_item.id],
                )
            ]
        )
    )
    state = {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    result = await build_radar_graph(
        llm_provider=provider,
        source_provider=FakeSourceProvider([source_item]),
    ).ainvoke(state)

    assert len(result["events"]) == 1
    assert result["signals"] == []
    assert [call["response_model"] for call in provider.calls] == [
        EventClusteringResponse,
        SignalDetectionResponse,
    ]
    assert result["metadata"]["event_count"] == 1
    assert result["metadata"]["execution_trace"][:4] == [
        "collect_sources",
        "normalize_sources",
        "cluster_events",
        "detect_signals",
    ]