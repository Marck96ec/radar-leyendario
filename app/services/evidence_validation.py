import json
from uuid import UUID

from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.signal import Signal
from app.services.models.evidence_validation import EvidenceValidationResponse
from app.services.ports.llm import LLMProvider
from app.services.prompts.evidence_validation import (
    SYSTEM_PROMPT,
    build_user_prompt,
)


def _build_eligible_sources(
    signals: list[Signal], events: list[Event]
) -> tuple[dict[UUID, set[UUID]], dict[UUID, object]]:
    events_by_id = {event.id: event for event in events}
    eligible_source_ids: dict[UUID, set[UUID]] = {}
    source_items_by_id: dict[UUID, object] = {}

    for signal in signals:
        source_ids: set[UUID] = set()
        for event_id in signal.related_event_ids:
            event = events_by_id.get(event_id)
            if event is None:
                continue
            for source_item in event.source_items:
                source_ids.add(source_item.id)
                source_items_by_id[source_item.id] = source_item
        eligible_source_ids[signal.id] = source_ids

    return eligible_source_ids, source_items_by_id


def _serialize_signals_and_sources(
    signals: list[Signal],
    eligible_source_ids: dict[UUID, set[UUID]],
    source_items_by_id: dict[UUID, object],
) -> str:
    return json.dumps(
        [
            {
                "signal": {
                    "id": str(signal.id),
                    "title": signal.title,
                    "description": signal.description,
                    "related_event_ids": [
                        str(event_id) for event_id in signal.related_event_ids
                    ],
                },
                "eligible_source_items": [
                    {
                        "id": str(source_item.id),
                        "title": source_item.title,
                        "source_name": source_item.source_name,
                        "published_at": source_item.published_at.isoformat(),
                        "content": source_item.content,
                    }
                    for source_item_id in sorted(
                        eligible_source_ids[signal.id], key=str
                    )
                    if (source_item := source_items_by_id[source_item_id])
                ],
            }
            for signal in signals
        ],
        ensure_ascii=True,
        indent=2,
    )


async def validate_evidence(
    signals: list[Signal],
    events: list[Event],
    llm_provider: LLMProvider,
) -> list[Evidence]:
    if not signals:
        return []

    eligible_source_ids, source_items_by_id = _build_eligible_sources(signals, events)
    if not any(eligible_source_ids.values()):
        return []

    response = await llm_provider.structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(
            _serialize_signals_and_sources(
                signals, eligible_source_ids, source_items_by_id
            )
        ),
        response_model=EvidenceValidationResponse,
    )
    signal_ids = {signal.id for signal in signals}
    seen: set[tuple[UUID, UUID, object]] = set()
    evidence: list[Evidence] = []

    for candidate in response.evidence:
        if candidate.signal_id not in signal_ids:
            continue
        if candidate.source_item_id not in eligible_source_ids[candidate.signal_id]:
            continue

        duplicate_key = (
            candidate.signal_id,
            candidate.source_item_id,
            candidate.evidence_type,
        )
        if duplicate_key in seen:
            continue
        seen.add(duplicate_key)
        evidence.append(
            Evidence(
                signal_id=candidate.signal_id,
                source_item_id=candidate.source_item_id,
                evidence_type=candidate.evidence_type,
                explanation=candidate.explanation,
                confidence=candidate.confidence,
            )
        )

    return evidence