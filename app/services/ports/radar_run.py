from typing import Protocol

from app.graph.state import RadarState


class RadarRunRepository(Protocol):
    def save(self, run_result: RadarState) -> None:
        ...

    def get_by_id(self, run_id: str) -> RadarState | None:
        ...
