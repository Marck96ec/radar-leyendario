import json
from uuid import UUID

from app.domain.event import Event
from app.domain.signal import Signal
from app.services.prompts.signal_detection import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.models.signal_detection import SignalDetectionResponse
from app.services.ports.llm import LLMProvider


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


async def detect_signals(
    events: list[Event],
    llm_provider: LLMProvider,
) -> list[Signal]:
    if not events:
        return []

    response = await llm_provider.structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(_serialize_events(events)),
        response_model=SignalDetectionResponse,
    )
    event_ids = {event.id for event in events}
    signals: list[Signal] = []

    for candidate in response.signals:
        related_event_ids = [
            event_id
            for event_id in candidate.related_event_ids
            if event_id in event_ids
        ]
        if not related_event_ids:
            continue

        signals.append(
            Signal(
                title=candidate.title,
                description=candidate.description,
                relevance_score=candidate.relevance_score,
                novelty_score=candidate.novelty_score,
                confidence_score=candidate.confidence_score,
                topics=candidate.topics,
                related_event_ids=related_event_ids,
            )
        )

    return signals