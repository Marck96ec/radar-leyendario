import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.graph.state import RadarState


class SQLiteRadarRunRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS radar_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _serialize_state(state: RadarState) -> str:
        payload: dict[str, Any] = {
            "run_id": state["run_id"],
            "source_items": [item.model_dump(mode="json") for item in state["source_items"]],
            "events": [item.model_dump(mode="json") for item in state["events"]],
            "signals": [item.model_dump(mode="json") for item in state["signals"]],
            "evidence": [item.model_dump(mode="json") for item in state["evidence"]],
            "opportunities": [
                item.model_dump(mode="json") for item in state["opportunities"]
            ],
            "ranked_opportunities": [
                item.model_dump(mode="json")
                for item in state["ranked_opportunities"]
            ],
            "errors": state["errors"],
            "metadata": state["metadata"],
        }
        return json.dumps(payload)

    @staticmethod
    def _deserialize_state(payload: str) -> RadarState:
        data = json.loads(payload)
        return {
            "run_id": data["run_id"],
            "source_items": [SourceItem.model_validate(item) for item in data["source_items"]],
            "events": [Event.model_validate(item) for item in data["events"]],
            "signals": [Signal.model_validate(item) for item in data["signals"]],
            "evidence": [Evidence.model_validate(item) for item in data["evidence"]],
            "opportunities": [
                Opportunity.model_validate(item) for item in data["opportunities"]
            ],
            "ranked_opportunities": [
                Opportunity.model_validate(item)
                for item in data["ranked_opportunities"]
            ],
            "errors": data["errors"],
            "metadata": data["metadata"],
        }

    def save(self, run_result: RadarState) -> None:
        payload = self._serialize_state(run_result)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO radar_runs (run_id, payload) VALUES (?, ?)",
                (run_result["run_id"], payload),
            )

    def get_by_id(self, run_id: str) -> RadarState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM radar_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._deserialize_state(row[0]) if row else None


class InMemoryRadarRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, RadarState] = {}

    def save(self, run_result: RadarState) -> None:
        self._runs[run_result["run_id"]] = deepcopy(run_result)

    def get_by_id(self, run_id: str) -> RadarState | None:
        run_result = self._runs.get(run_id)
        return deepcopy(run_result) if run_result is not None else None
