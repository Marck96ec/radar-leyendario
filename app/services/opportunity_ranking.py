from app.domain.opportunity import Opportunity


FINAL_SCORE_WEIGHTS = {
    "impact_score": 0.25,
    "timing_score": 0.20,
    "novelty_score": 0.20,
    "content_potential": 0.15,
    "business_potential": 0.10,
    "evidence_confidence": 0.10,
}


def _calculate_final_score(opportunity: Opportunity) -> float:
    score = sum(
        getattr(opportunity, attribute) * weight
        for attribute, weight in FINAL_SCORE_WEIGHTS.items()
    )
    return round(score, 2)


def rank_opportunities(
    opportunities: list[Opportunity],
    limit: int = 3,
) -> list[Opportunity]:
    ranked = [
        opportunity.model_copy(
            update={"final_score": _calculate_final_score(opportunity)}
        )
        for opportunity in opportunities
    ]
    ranked.sort(key=lambda opportunity: opportunity.final_score or 0, reverse=True)
    return ranked[:limit]