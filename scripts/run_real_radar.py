import asyncio
import sys
import traceback
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings
from app.domain.source_item import SourceItem
from app.infrastructure.llm.openai_provider import OpenAILLMProvider
from app.infrastructure.sources.config import load_enabled_feeds
from app.infrastructure.sources.rss_provider import RSSSourceProvider
from app.services.ports.source import SourceProvider
from app.services.radar_runner import run_radar
from app.services.source_selection import select_balanced_items


class StaticSourceProvider:
    def __init__(self, source_items: list[SourceItem]) -> None:
        self._source_items = list(source_items)

    async def fetch(self) -> list[SourceItem]:
        return list(self._source_items)


async def main() -> None:
    rss_provider = RSSSourceProvider(load_enabled_feeds())
    fetched_items = await rss_provider.fetch()
    analyzed_items = select_balanced_items(fetched_items)

    settings = get_settings()
    llm_provider = OpenAILLMProvider(settings)
    static_source_provider: SourceProvider = StaticSourceProvider(analyzed_items)
    state = await run_radar(llm_provider, static_source_provider)

    print("=====================================")
    print("RADAR LEYENDARIO IA — REAL SMOKE TEST")
    print("=====================================")
    print(f"Sources fetched total: {len(fetched_items)}")
    print(f"Sources analyzed: {len(analyzed_items)}")
    print(f"Events: {len(state['events'])}")
    print(f"Signals: {len(state['signals'])}")
    print(f"Evidence: {len(state['evidence'])}")
    print(f"Opportunities: {len(state['opportunities'])}")
    print(f"Ranked opportunities: {len(state['ranked_opportunities'])}")

    print("\n--- SOURCE DISTRIBUTION ---")
    for source_name, count in sorted(Counter(item.source_name for item in analyzed_items).items()):
        print(f"{source_name}: {count}")

    print("\n--- SOURCES ANALYZED ---")
    for index, source in enumerate(analyzed_items, start=1):
        print(f"\n[{index}]")
        print(f"source_name: {source.source_name}")
        print(f"published_at: {source.published_at}")
        print(f"title: {source.title}")
        print(f"url: {source.url}")

    print("\n--- EVENTS ---")
    for index, event in enumerate(state["events"], start=1):
        print(f"\nEVENT {index}")
        print(f"title: {event.title}")
        print(f"summary: {event.summary}")
        print(f"sources: {len(event.source_items)}")

    print("\n--- SIGNALS ---")
    for index, signal in enumerate(state["signals"], start=1):
        print(f"\nSIGNAL {index}")
        print(f"title: {signal.title}")
        print(f"description: {signal.description}")
        print(f"relevance: {signal.relevance_score}")
        print(f"novelty: {signal.novelty_score}")
        print(f"confidence: {signal.confidence_score}")
        print(f"related events: {len(signal.related_event_ids)}")

    print("\n--- EVIDENCE ---")
    for evidence in state["evidence"]:
        print("\ntype:", evidence.evidence_type.value)
        print("confidence:", evidence.confidence)
        print("explanation:", evidence.explanation)
        print("source_item_id:", evidence.source_item_id)

    print("\n--- OPPORTUNITIES ---")
    for opportunity in state["opportunities"]:
        print(f"\ntitle: {opportunity.title}")
        print(f"category: {opportunity.category.value}")
        print(f"why_now: {opportunity.why_now}")
        print(f"impact_score: {opportunity.impact_score}")
        print(f"timing_score: {opportunity.timing_score}")
        print(f"novelty_score: {opportunity.novelty_score}")
        print(f"content_potential: {opportunity.content_potential}")
        print(f"business_potential: {opportunity.business_potential}")
        print(f"evidence_confidence: {opportunity.evidence_confidence}")

    print("\n=====================================")
    print("TOP 3 RADAR LEYENDARIO")
    print("=====================================")
    for index, opportunity in enumerate(state["ranked_opportunities"][:3], start=1):
        print(f"\n#{index}")
        print(f"title: {opportunity.title}")
        print(f"category: {opportunity.category.value}")
        print(f"final_score: {opportunity.final_score}")
        print(f"why_now: {opportunity.why_now}")

    print("\nexecution_trace:", state["metadata"].get("execution_trace", []))
    print("metadata:", state["metadata"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"\nException type: {type(exc).__name__}", file=sys.stderr)
        print(f"Exception message: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1) from exc