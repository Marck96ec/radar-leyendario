import json
import logging
from collections.abc import MutableMapping
from uuid import UUID

from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.services.models.evidence_validation import EvidenceValidationResponse
from app.services.ports.llm import LLMProvider
from app.services.prompts.evidence_validation import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.score_normalization import normalize_percentage_score

logger = logging.getLogger(__name__)


def _build_eligible_sources(
    signals: list[Signal], events: list[Event]
) -> tuple[dict[UUID, set[UUID]], dict[UUID, SourceItem]]:
    events_by_id = {event.id: event for event in events}
    eligible_source_ids: dict[UUID, set[UUID]] = {}
    source_items_by_id: dict[UUID, SourceItem] = {}

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
                        "content_length": len(source_item.content),
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
    metrics: MutableMapping[str, object] | None = None,
) -> list[Evidence]:
    if not signals:
        return []

    eligible_source_ids, source_items_by_id = _build_eligible_sources(signals, events)
    if metrics is not None:
        metrics["eligible_sources"] = len(source_items_by_id)
        metrics["evidence_proposed"] = 0
        metrics["evidence_accepted"] = 0
        metrics["candidates_discarded"] = 0
        metrics["discard_reasons"] = {}
    if not any(eligible_source_ids.values()):
        if metrics is not None:
            metrics["discard_reasons"] = {"no_eligible_sources": 1}
        logger.warning(
            "Evidence validation skipped: signals have no eligible source items",
            extra={"signal_count": len(signals)},
        )
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
    if metrics is not None:
        metrics["evidence_proposed"] = len(response.evidence)
    signal_ids = {signal.id for signal in signals}
    seen: set[tuple[UUID, UUID, object]] = set()
    evidence: list[Evidence] = []

    for candidate in response.evidence:
        if candidate.signal_id not in signal_ids:
            _record_discard(metrics, "unknown_signal_id")
            continue
        if candidate.source_item_id not in eligible_source_ids[candidate.signal_id]:
            _record_discard(metrics, "source_not_eligible_for_signal")
            continue

        duplicate_key = (
            candidate.signal_id,
            candidate.source_item_id,
            candidate.evidence_type,
        )
        if duplicate_key in seen:
            _record_discard(metrics, "duplicate_candidate")
            continue
        seen.add(duplicate_key)
        evidence.append(
            Evidence(
                signal_id=candidate.signal_id,
                source_item_id=candidate.source_item_id,
                evidence_type=candidate.evidence_type,
                explanation=candidate.explanation,
                confidence=normalize_percentage_score(candidate.confidence),
            )
        )

    if metrics is not None:
        metrics["evidence_accepted"] = len(evidence)
        if not response.evidence:
            metrics["discard_reasons"] = {
                **(
                    metrics.get("discard_reasons", {})
                    if isinstance(metrics.get("discard_reasons"), dict)
                    else {}
                ),
                "model_returned_no_evidence": 1,
            }
    if not evidence:
        logger.warning(
            "Evidence validation returned no accepted evidence",
            extra={
                "signal_count": len(signals),
                "eligible_source_count": len(source_items_by_id),
                "proposed_count": len(response.evidence),
            },
        )
    return evidence


def _record_discard(metrics: MutableMapping[str, object] | None, reason: str) -> None:
    if metrics is None:
        return
    metrics["candidates_discarded"] = int(metrics.get("candidates_discarded", 0)) + 1
    reasons = metrics.setdefault("discard_reasons", {})
    if isinstance(reasons, dict):
        reasons[reason] = int(reasons.get(reason, 0)) + 1