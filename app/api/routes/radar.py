from typing import cast

from fastapi import APIRouter
from pydantic import BaseModel

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
def run_radar_endpoint() -> RadarRunResponse:
    state = run_radar()
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
