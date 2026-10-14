from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID

from app.core.dependencies import (
    get_llm_provider,
    get_radar_run_repository,
    get_source_provider,
)
from app.domain.event import Event
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.services.ports.radar_run import RadarRunRepository
from app.services.ports.llm import LLMProvider
from app.services.ports.source import SourceProvider
from app.services.radar_runner import run_radar


router = APIRouter()


class RadarRunResponse(BaseModel):
    run_id: str
    status: str
    sources: int
    events: int
    signals: int
    opportunities: int
    execution_trace: list[str]


class RadarRunSummary(BaseModel):
    sources: int
    events: int
    signals: int
    opportunities: int


class RadarRunDetailsResponse(BaseModel):
    run_id: str
    status: str
    summary: RadarRunSummary
    ranked_opportunities: list[Opportunity]
    top_opportunity: Opportunity | None
    signals: list[Signal]
    events: list[Event]
    execution_trace: list[str]


@router.post("/run", response_model=RadarRunResponse)
async def run_radar_endpoint(
    llm_provider: LLMProvider = Depends(get_llm_provider),
    source_provider: SourceProvider = Depends(get_source_provider),
    repository: RadarRunRepository = Depends(get_radar_run_repository),
) -> RadarRunResponse:
    state = await run_radar(llm_provider, source_provider, repository)
    execution_trace = cast(list[str], state["metadata"].get("execution_trace", []))

    return RadarRunResponse(
        run_id=state["run_id"],
        status="completed",
        sources=len(state["source_items"]),
        events=len(state["events"]),
        signals=len(state["signals"]),
        opportunities=len(state["opportunities"]),
        execution_trace=execution_trace,
    )


@router.get("/runs/{run_id}", response_model=RadarRunDetailsResponse)
async def get_radar_run_endpoint(
    run_id: UUID,
    repository: RadarRunRepository = Depends(get_radar_run_repository),
) -> RadarRunDetailsResponse:
    state = repository.get_by_id(str(run_id))
    if state is None:
        raise HTTPException(status_code=404, detail="Radar run not found")

    ranked_opportunities = state["ranked_opportunities"]
    execution_trace = state["metadata"].get("execution_trace", [])
    return RadarRunDetailsResponse(
        run_id=state["run_id"],
        status="completed",
        summary=RadarRunSummary(
            sources=len(state["source_items"]),
            events=len(state["events"]),
            signals=len(state["signals"]),
            opportunities=len(ranked_opportunities),
        ),
        ranked_opportunities=ranked_opportunities,
        top_opportunity=ranked_opportunities[0] if ranked_opportunities else None,
        signals=state["signals"],
        events=state["events"],
        execution_trace=list(execution_trace),
    )
