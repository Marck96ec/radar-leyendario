import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings
from app.domain.enums import SourceType
from app.domain.source_item import SourceItem
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.services.event_clustering import cluster_events


def build_source_items() -> list[SourceItem]:
    published_at = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    return [
        SourceItem(
            source_name="NovaAI Official Blog",
            source_type=SourceType.OFFICIAL,
            title="NovaAI launches Nova Agent Platform",
            content=(
                "NovaAI announced Nova Agent Platform, a new platform for building "
                "and operating enterprise AI agents. The launch includes orchestration, "
                "tool integrations, execution controls and monitoring."
            ),
            url="https://example.test/novaai-agent-platform-official",
            published_at=published_at,
        ),
        SourceItem(
            source_name="Tech Media A",
            source_type=SourceType.MEDIA,
            title="NovaAI introduces enterprise platform for AI agents",
            content=(
                "NovaAI has released Nova Agent Platform, its new system for teams "
                "building enterprise AI agents. The product includes orchestration, "
                "tool connectivity and controls for agent execution."
            ),
            url="https://example.test/tech-media-a-nova-agent-platform",
            published_at=published_at,
        ),
        SourceItem(
            source_name="Industry News",
            source_type=SourceType.MEDIA,
            title="New Nova Agent Platform targets enterprise agent workflows",
            content=(
                "NovaAI unveiled Nova Agent Platform today. The new offering is aimed "
                "at enterprise agent workflows and provides orchestration, integrations, "
                "monitoring and execution controls."
            ),
            url="https://example.test/industry-news-nova-agent-platform",
            published_at=published_at,
        ),
        SourceItem(
            source_name="Tech Media B",
            source_type=SourceType.MEDIA,
            title="NovaAI cuts inference API prices by 30 percent",
            content=(
                "NovaAI announced a 30 percent reduction in inference API pricing "
                "for several production models. The pricing change takes effect "
                "next month."
            ),
            url="https://example.test/tech-media-b-inference-prices",
            published_at=published_at,
        ),
        SourceItem(
            source_name="Developer News",
            source_type=SourceType.MEDIA,
            title="NovaAI announces lower model inference pricing",
            content=(
                "NovaAI is lowering inference API prices for several models. "
                "The company says the new rates will become available next month."
            ),
            url="https://example.test/developer-news-inference-pricing",
            published_at=published_at,
        ),
        SourceItem(
            source_name="Research News",
            source_type=SourceType.MEDIA,
            title="University releases open benchmark for robotics reasoning",
            content=(
                "A university research group released a new public benchmark "
                "for evaluating reasoning in autonomous robotics systems. "
                "The benchmark is unrelated to NovaAI."
            ),
            url="https://example.test/research-news-robotics-benchmark",
            published_at=published_at,
        ),
    ]


async def main() -> None:
    source_items = build_source_items()
    settings = get_settings()
    llm_provider = OpenAILLMProvider(settings)
    events = await cluster_events(source_items, llm_provider)

    print("=====================================")
    print("RADAR — EVENT CLUSTERING EXPERIMENT")
    print("=====================================")
    print(f"Input SourceItems: {len(source_items)}")
    print(f"Output Events: {len(events)}")

    print("\n--- INPUT ---")
    for index, source_item in enumerate(source_items, start=1):
        print(f"\nSOURCE {index}")
        print(f"source: {source_item.source_name}")
        print(f"title: {source_item.title}")

    print("\n--- CLUSTERED EVENTS ---")
    for index, event in enumerate(events, start=1):
        print(f"\nEVENT {index}")
        print(f"title: {event.title}")
        print(f"summary: {event.summary}")
        print(f"sources: {len(event.source_items)}")
        for source_item in event.source_items:
            print(f"  - {source_item.source_name}: {source_item.title}")
        print("source_item_ids:")
        for source_item in event.source_items:
            print(f"  - {source_item.id}")

    actual_cluster_sizes = [len(event.source_items) for event in events]
    print("\n--- EXPECTATION ---")
    print("Expected cluster sizes: [3, 2, 1]")
    print(f"Actual cluster sizes: {actual_cluster_sizes}")
    print("Expected events: 3")
    print(f"Actual events: {len(events)}")

    print("\nRESULT:")
    if sorted(actual_cluster_sizes, reverse=True) == [3, 2, 1]:
        print("PASS — semantic clustering matched expected structure")
    else:
        print("OBSERVE — clustering differed from expected structure")

    assigned_ids = [source_item.id for event in events for source_item in event.source_items]
    total_assignments = len(assigned_ids)
    unique_assignments = len(set(assigned_ids))
    input_sources = len(source_items)
    print("\nTotal source assignments:", total_assignments)
    print("Unique source assignments:", unique_assignments)
    print("Input sources:", input_sources)
    if (
        total_assignments == input_sources
        and unique_assignments == input_sources
    ):
        print("Source integrity: PASS")
    else:
        print("Source integrity: REVIEW")


if __name__ == "__main__":
    asyncio.run(main())