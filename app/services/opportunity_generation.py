import json
from uuid import UUID

from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.services.models.opportunity_generation import OpportunityGenerationResponse
from app.services.ports.llm import LLMProvider
from app.services.prompts.opportunity_generation import (
    SYSTEM_PROMPT,
    build_user_prompt,
)


def _serialize_signal_grounding(
    signal: Signal,
    evidence: list[Evidence],
    source_items_by_id: dict[UUID, SourceItem],
) -> str:
    return json.dumps(
        {
            "signal": {
                "id": str(signal.id),
                "title": signal.title,
                "description": signal.description,
                "scores": {
                    "relevance": signal.relevance_score,
                    "novelty": signal.novelty_score,
                    "confidence": signal.confidence_score,
                },
                "topics": signal.topics,
            },
            "evidence": [
                {
                    "evidence_type": item.evidence_type,
                    "explanation": item.explanation,
                    "confidence": item.confidence,
                    "source_item": {
                        "id": str(source_item.id),
                        "title": source_item.title,
                        "url": source_item.url,
                        "source_name": source_item.source_name,
                        "published_at": source_item.published_at.isoformat(),
                        "content": source_item.content,
                    },
                }
                for item in evidence
                if (source_item := source_items_by_id.get(item.source_item_id))
            ],
        },
        ensure_ascii=True,
        indent=2,
        default=str,
    )


async def generate_opportunities(
    signals: list[Signal],
    evidence: list[Evidence],
    source_items: list[SourceItem],
    llm_provider: LLMProvider,
) -> list[Opportunity]:
    if not signals:
        return []

    source_items_by_id = {source_item.id: source_item for source_item in source_items}
    evidence_by_signal: dict[UUID, list[Evidence]] = {signal.id: [] for signal in signals}
    for item in evidence:
        if item.signal_id in evidence_by_signal and item.source_item_id in source_items_by_id:
            evidence_by_signal[item.signal_id].append(item)

    opportunities: list[Opportunity] = []
    signal_ids = set(evidence_by_signal)
    for signal in signals:
        response = await llm_provider.structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                _serialize_signal_grounding(
                    signal, evidence_by_signal[signal.id], source_items_by_id
                )
            ),
            response_model=OpportunityGenerationResponse,
        )
        if not evidence_by_signal[signal.id]:
            continue

        valid_candidates = [
            candidate
            for candidate in response.opportunities
            if candidate.signal_id in signal_ids and candidate.signal_id == signal.id
        ]
        for candidate in valid_candidates[:3]:
            opportunities.append(
                Opportunity(
                    signal_id=candidate.signal_id,
                    title=candidate.title,
                    description=candidate.description,
                    why_now=candidate.why_now,
                    category=candidate.category,
                    impact_score=candidate.impact_score,
                    timing_score=candidate.timing_score,
                    novelty_score=candidate.novelty_score,
                    content_potential=candidate.content_potential,
                    business_potential=candidate.business_potential,
                    evidence_confidence=candidate.evidence_confidence,
                )
            )

    return opportunities