import logging
from datetime import datetime
from time import perf_counter
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.dependencies import (
    get_llm_provider,
    get_run_repository,
    get_source_provider,
    require_radar_access,
)
from app.domain.enums import EvidenceType, OpportunityCategory, SourceType
from app.graph.state import RadarState
from app.repositories.runs import RunRecord, RunRepository, utc_now
from app.services.ports.llm import LLMProvider
from app.services.ports.source import SourceProvider
from app.services.radar_runner import run_radar


logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_radar_access)])


class RadarRunRequest(BaseModel):
    run_id: UUID | None = Field(
        default=None,
        description="Optional client-generated identifier for safe retries.",
    )


class RadarRunResponse(BaseModel):
    run_id: str
    status: str
    sources: int
    events: int
    signals: int
    opportunities: int
    execution_trace: list[str]
    duration_ms: float | None = None
    started_at: str | None = None
    completed_at: str | None = None
    errors: list[str] = Field(default_factory=list)


class SourceResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    title: str
    url: str
    source_name: str
    published_at: datetime
    source_type: SourceType


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    signal_id: UUID
    source_item_id: UUID
    evidence_type: EvidenceType
    explanation: str
    confidence: float


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    title: str
    problem_or_opportunity: str | None
    description: str
    why_now: str
    category: OpportunityCategory
    impact_score: float
    timing_score: float
    novelty_score: float
    content_potential: float
    business_potential: float
    evidence_confidence: float
    final_score: float | None
    evidences: list[EvidenceResponse]
    sources: list[SourceResponse]


def _state_counts(state: RadarState | None) -> dict[str, int]:
    if state is None:
        return {
            "sources": 0,
            "events": 0,
            "signals": 0,
            "opportunities": 0,
        }
    return {
        "sources": len(state["source_items"]),
        "events": len(state["events"]),
        "signals": len(state["signals"]),
        "opportunities": len(state["opportunities"]),
    }


def _run_response(record: RunRecord) -> RadarRunResponse:
    state = record.state
    metadata = state["metadata"] if state else {}
    trace = cast(list[str], metadata.get("execution_trace", []))
    counts = _state_counts(state)
    return RadarRunResponse(
        run_id=record.run_id,
        status=record.status,
        **counts,
        execution_trace=trace,
        duration_ms=record.duration_ms,
        started_at=record.started_at,
        completed_at=record.completed_at,
        errors=state["errors"] if state else ([record.error] if record.error else []),
    )


def _opportunity_response(
    opportunity_id: UUID, state: RadarState
) -> OpportunityResponse | None:
    opportunity = next(
        (
            candidate
            for candidate in state["ranked_opportunities"]
            if candidate.id == opportunity_id
        ),
        None,
    )
    if opportunity is None:
        return None

    evidences = [
        item for item in state["evidence"] if item.signal_id == opportunity.signal_id
    ]
    source_ids = {item.source_item_id for item in evidences}
    sources = [item for item in state["source_items"] if item.id in source_ids]
    return OpportunityResponse(
        id=opportunity.id,
        title=opportunity.title,
        problem_or_opportunity=opportunity.title,
        description=opportunity.description,
        why_now=opportunity.why_now,
        category=opportunity.category,
        impact_score=opportunity.impact_score,
        timing_score=opportunity.timing_score,
        novelty_score=opportunity.novelty_score,
        content_potential=opportunity.content_potential,
        business_potential=opportunity.business_potential,
        evidence_confidence=opportunity.evidence_confidence,
        final_score=opportunity.final_score,
        evidences=[
            EvidenceResponse.model_validate(item.model_dump()) for item in evidences
        ],
        sources=[
            SourceResponse.model_validate(item.model_dump()) for item in sources
        ],
    )


def _get_record(repository: RunRepository, run_id: str) -> RunRecord:
    record = repository.get(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Radar run {run_id} was not found",
        )
    return record


@router.post("/run", response_model=RadarRunResponse)
async def run_radar_endpoint(
    request: RadarRunRequest | None = None,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    source_provider: SourceProvider = Depends(get_source_provider),
    repository: RunRepository = Depends(get_run_repository),
) -> RadarRunResponse:
    run_id = str(request.run_id if request and request.run_id else uuid4())
    existing = repository.get(run_id)
    if existing is not None:
        return _run_response(existing)

    started_at = utc_now()
    started = perf_counter()
    repository.create_running(run_id, started_at)
    try:
        state = await run_radar(llm_provider, source_provider, run_id=run_id)
        completed_at = utc_now()
        duration_ms = round((perf_counter() - started) * 1000, 2)
        repository.save_completed(state, started_at, completed_at, duration_ms)
    except Exception as exc:
        completed_at = utc_now()
        duration_ms = round((perf_counter() - started) * 1000, 2)
        repository.save_failed(
            run_id, started_at, completed_at, duration_ms, type(exc).__name__
        )
        logger.exception("Radar run failed", extra={"run_id": run_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Radar execution failed; consult logs with the run_id",
        ) from exc

    record = repository.get(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Radar run completed but could not be recovered",
        )
    return _run_response(record)


@router.get("/runs/{run_id}", response_model=RadarRunResponse)
def get_radar_run(
    run_id: UUID, repository: RunRepository = Depends(get_run_repository)
) -> RadarRunResponse:
    return _run_response(_get_record(repository, str(run_id)))


@router.get(
    "/runs/{run_id}/opportunities", response_model=list[OpportunityResponse]
)
def list_radar_opportunities(
    run_id: UUID, repository: RunRepository = Depends(get_run_repository)
) -> list[OpportunityResponse]:
    record = _get_record(repository, str(run_id))
    if record.state is None:
        return []
    return [
        opportunity
        for item in record.state["ranked_opportunities"]
        if (opportunity := _opportunity_response(item.id, record.state)) is not None
    ]


@router.get(
    "/runs/{run_id}/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
)
def get_radar_opportunity(
    run_id: UUID,
    opportunity_id: UUID,
    repository: RunRepository = Depends(get_run_repository),
) -> OpportunityResponse:
    record = _get_record(repository, str(run_id))
    if record.state is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Radar run has no completed state",
        )
    opportunity = _opportunity_response(opportunity_id, record.state)
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opportunity {opportunity_id} was not found in run {run_id}",
        )
    return opportunity
