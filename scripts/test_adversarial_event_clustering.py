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
			title="NovaAI launches Agent Platform 2.0",
			content=(
				"NovaAI announced the release of Agent Platform 2.0 today. "
				"The release adds persistent agent memory, improved tool orchestration, "
				"and new observability capabilities."
			),
			url="https://example.test/novaai-official-agent-platform-2-launch",
			published_at=published_at,
		),
		SourceItem(
			source_name="Tech Media A",
			source_type=SourceType.MEDIA,
			title="NovaAI releases new Agent Platform 2.0",
			content=(
				"NovaAI has launched version 2.0 of its Agent Platform. "
				"The new release includes persistent memory, orchestration improvements "
				"and observability features for enterprise agent applications."
			),
			url="https://example.test/tech-media-a-agent-platform-2-launch",
			published_at=published_at,
		),
		SourceItem(
			source_name="Tech Media B",
			source_type=SourceType.MEDIA,
			title="NovaAI Agent Platform 2.0 suffers service disruption",
			content=(
				"Several hours after the Agent Platform 2.0 release, NovaAI reported "
				"a service disruption affecting some agent executions. The company said "
				"engineers were investigating the incident."
			),
			url="https://example.test/tech-media-b-agent-platform-2-incident",
			published_at=published_at,
		),
		SourceItem(
			source_name="Industry News",
			source_type=SourceType.MEDIA,
			title="NovaAI investigates Agent Platform 2.0 outage",
			content=(
				"NovaAI is investigating an outage affecting Agent Platform 2.0. "
				"The incident began after the new version had already been released "
				"and impacted some production agent workloads."
			),
			url="https://example.test/industry-news-agent-platform-2-incident",
			published_at=published_at,
		),
		SourceItem(
			source_name="Developer News",
			source_type=SourceType.MEDIA,
			title="NovaAI changes Agent Platform 2.0 pricing",
			content=(
				"NovaAI announced a new pricing model for Agent Platform 2.0. "
				"The company introduced usage-based pricing for agent executions "
				"starting next month."
			),
			url="https://example.test/developer-news-agent-platform-2-pricing",
			published_at=published_at,
		),
		SourceItem(
			source_name="Cloud Media",
			source_type=SourceType.MEDIA,
			title="Agent Platform 2.0 gets new usage-based pricing",
			content=(
				"NovaAI published new pricing for Agent Platform 2.0. Agent executions "
				"will move to a usage-based pricing structure beginning next month."
			),
			url="https://example.test/cloud-media-agent-platform-2-pricing",
			published_at=published_at,
		),
	]


async def main() -> None:
	source_items = build_source_items()
	settings = get_settings()
	llm_provider = OpenAILLMProvider(settings)
	events = await cluster_events(source_items, llm_provider)

	print("========================================")
	print("RADAR — ADVERSARIAL EVENT CLUSTERING")
	print("========================================")
	print(f"Input SourceItems: {len(source_items)}")
	print(f"Output Events: {len(events)}")

	print("\n--- INPUT ---")
	for index, source_item in enumerate(source_items, start=1):
		print(f"\nSOURCE {index}")
		print(f"source: {source_item.source_name}")
		print(f"title: {source_item.title}")

	print("\n--- EVENTS ---")
	for index, event in enumerate(events, start=1):
		print(f"\nEVENT {index}")
		print(f"title: {event.title}")
		print(f"summary: {event.summary}")
		print(f"sources: {len(event.source_items)}")
		print("source titles:")
		for source_item in event.source_items:
			print(f"  - {source_item.title}")
		print("source_item_ids:")
		for source_item in event.source_items:
			print(f"  - {source_item.id}")

	actual_cluster_sizes = [len(event.source_items) for event in events]
	print("\nExpected cluster sizes: [2, 2, 2]")
	print(f"Actual cluster sizes: {actual_cluster_sizes}")
	print("Expected events: 3")
	print(f"Actual events: {len(events)}")

	assigned_ids = [
		source_item.id for event in events for source_item in event.source_items
	]
	total_assignments = len(assigned_ids)
	unique_assignments = len(set(assigned_ids))
	input_sources = len(source_items)

	print("\nRESULT:")
	if (
		len(events) == 3
		and actual_cluster_sizes == [2, 2, 2]
		and total_assignments == input_sources
		and unique_assignments == input_sources
	):
		print("PASS — structural clustering matched expectation")
	else:
		print("OBSERVE — clustering differed from expected structure")

	print("\n--- SEMANTIC REVIEW ---")
	print("Grouped titles for human inspection:")
	for index, event in enumerate(events, start=1):
		titles = [source_item.title for source_item in event.source_items]
		print(f"Event {index}: {titles}")

	print("\nTotal source assignments:", total_assignments)
	print("Unique source assignments:", unique_assignments)
	print("Input sources:", input_sources)
	if total_assignments == input_sources and unique_assignments == input_sources:
		print("Source integrity: PASS")
	else:
		print("Source integrity: REVIEW")


if __name__ == "__main__":
	asyncio.run(main())
