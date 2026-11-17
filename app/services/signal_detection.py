import json
import re
from collections.abc import MutableMapping

from app.domain.event import Event
from app.domain.signal import Signal
from app.services.prompts.signal_detection import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.models.signal_detection import SignalDetectionResponse
from app.services.ports.llm import LLMProvider
from app.services.score_normalization import normalize_percentage_score


def _serialize_events(events: list[Event]) -> str:
    return json.dumps(
        [
            {
                "id": str(event.id),
                "title": event.title,
                "summary": event.summary,
            }
            for event in events
        ],
        ensure_ascii=True,
        indent=2,
    )


_GENERIC_SIGNAL_TERMS = {
    "adoption",
    "becoming",
    "ecosystem",
    "growing",
    "growth",
    "landscape",
    "movement",
    "shift",
    "structural",
    "tendency",
    "trend",
    "trends",
    "tendencia",
    "tendencias",
    "creciente",
    "crecimiento",
    "ecosistema",
    "panorama",
}
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "an",
    "and",
    "are",
    "between",
    "from",
    "into",
    "more",
    "not",
    "of",
    "on",
    "or",
    "same",
    "that",
    "the",
    "their",
    "these",
    "this",
    "to",
    "with",
    "una",
    "uno",
    "los",
    "las",
    "del",
    "que",
    "con",
    "para",
    "entre",
}


def _meaningful_tokens(value: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-záéíóúüñ0-9]{4,}", value.lower())
        if token not in _STOP_WORDS
    }
    return tokens | {
        token[:-1]
        for token in tokens
        if token.endswith("s") and len(token) > 5
    }


def _discard_reason(
    candidate: object, related_events: list[Event]
) -> str | None:
    title = str(candidate.title)
    description = str(candidate.description)
    if len(related_events) == 1 and (
        _meaningful_tokens(title + " " + description) & _GENERIC_SIGNAL_TERMS
    ):
        return "general_signal_requires_multiple_events"
    if len(related_events) < 2:
        return None

    anchor_tokens = _meaningful_tokens(
        title + " " + description + " " + " ".join(candidate.topics)
    )
    event_tokens = [
        _meaningful_tokens(event.title + " " + event.summary)
        for event in related_events
    ]
    if not anchor_tokens or any(not tokens & anchor_tokens for tokens in event_tokens):
        return "related_events_do_not_support_same_conclusion"
    shared_tokens = set.intersection(*event_tokens)
    if not shared_tokens:
        return "related_events_lack_shared_fact"
    return None


def _record_discard(metrics: MutableMapping[str, object], reason: str) -> None:
    metrics["signals_discarded"] = int(metrics.get("signals_discarded", 0)) + 1
    reasons = metrics.setdefault("discard_reasons", {})
    if isinstance(reasons, dict):
        reasons[reason] = int(reasons.get(reason, 0)) + 1


async def detect_signals(
    events: list[Event],
    llm_provider: LLMProvider,
    metrics: MutableMapping[str, object] | None = None,
) -> list[Signal]:
    if not events:
        return []

    response = await llm_provider.structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(_serialize_events(events)),
        response_model=SignalDetectionResponse,
    )
    event_ids = {event.id for event in events}
    if metrics is not None:
        metrics["signals_proposed"] = len(response.signals)
        metrics["signals_discarded"] = 0
        metrics["discard_reasons"] = {}
    signals: list[Signal] = []

    for candidate in response.signals:
        related_event_ids = [
            event_id
            for event_id in candidate.related_event_ids
            if event_id in event_ids
        ]
        if not related_event_ids:
            if metrics is not None:
                _record_discard(metrics, "no_valid_related_event_ids")
            continue

        related_events = [
            event for event in events if event.id in related_event_ids
        ]
        reason = _discard_reason(candidate, related_events)
        if reason is not None:
            if metrics is not None:
                _record_discard(metrics, reason)
            continue

        signals.append(
            Signal(
                title=candidate.title,
                description=candidate.description,
                relevance_score=normalize_percentage_score(candidate.relevance_score),
                novelty_score=normalize_percentage_score(candidate.novelty_score),
                confidence_score=normalize_percentage_score(candidate.confidence_score),
                topics=candidate.topics,
                related_event_ids=related_event_ids,
            )
        )

    if metrics is not None:
        metrics["signals_accepted"] = len(signals)
    return signals