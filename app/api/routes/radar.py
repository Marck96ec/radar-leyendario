from typing import cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.dependencies import get_llm_provider
from app.services.ports.llm import LLMProvider
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


@router.post("/run", response_model=RadarRunResponse)
async def run_radar_endpoint(
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> RadarRunResponse:
    state = await run_radar(llm_provider)
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
