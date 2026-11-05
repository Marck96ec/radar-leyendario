import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from app.graph.state import RadarState


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    started_at: str
    completed_at: str | None
    duration_ms: float | None
    state: RadarState | None
    error: str | None


class RunRepository(Protocol):
    def create_running(self, run_id: str, started_at: str) -> None:
        ...

    def save_completed(
        self, state: RadarState, started_at: str, completed_at: str, duration_ms: float
    ) -> None:
        ...

    def save_failed(
        self,
        run_id: str,
        started_at: str,
        completed_at: str,
        duration_ms: float,
        error: str,
    ) -> None:
        ...

    def get(self, run_id: str) -> RunRecord | None:
        ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRunRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._memory_connection: sqlite3.Connection | None = None
        if database_path == ":memory:":
            self._memory_connection = sqlite3.connect(database_path, timeout=30)
            self._memory_connection.row_factory = sqlite3.Row
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS radar_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms REAL,
                    state_json TEXT,
                    error TEXT
                )
                """
            )

    def create_running(self, run_id: str, started_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO radar_runs (run_id, status, started_at)
                VALUES (?, 'running', ?)
                """,
                (run_id, started_at),
            )

    def save_completed(
        self, state: RadarState, started_at: str, completed_at: str, duration_ms: float
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE radar_runs
                SET status = 'completed', completed_at = ?, duration_ms = ?,
                    state_json = ?, error = NULL
                WHERE run_id = ?
                """,
                (
                    completed_at,
                    duration_ms,
                    json.dumps(_serialize_state(state)),
                    state["run_id"],
                ),
            )

    def save_failed(
        self,
        run_id: str,
        started_at: str,
        completed_at: str,
        duration_ms: float,
        error: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE radar_runs
                SET status = 'failed', completed_at = ?, duration_ms = ?, error = ?
                WHERE run_id = ?
                """,
                (completed_at, duration_ms, error, run_id),
            )

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, status, started_at, completed_at, duration_ms,
                       state_json, error
                FROM radar_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None
        state = (
            _deserialize_state(json.loads(row["state_json"]))
            if row["state_json"]
            else None
        )
        return RunRecord(
            run_id=row["run_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            state=state,
            error=row["error"],
        )


def _serialize_state(state: RadarState) -> dict[str, object]:
    return {
        "run_id": state["run_id"],
        "source_items": [item.model_dump(mode="json") for item in state["source_items"]],
        "events": [event.model_dump(mode="json") for event in state["events"]],
        "signals": [signal.model_dump(mode="json") for signal in state["signals"]],
        "evidence": [item.model_dump(mode="json") for item in state["evidence"]],
        "opportunities": [
            item.model_dump(mode="json") for item in state["opportunities"]
        ],
        "ranked_opportunities": [
            item.model_dump(mode="json") for item in state["ranked_opportunities"]
        ],
        "errors": list(state["errors"]),
        "metadata": state["metadata"],
    }


def _deserialize_state(payload: dict[str, object]) -> RadarState:
    from app.domain.event import Event
    from app.domain.evidence import Evidence
    from app.domain.opportunity import Opportunity
    from app.domain.signal import Signal
    from app.domain.source_item import SourceItem

    source_items = cast(list[object], payload["source_items"])
    events = cast(list[object], payload["events"])
    signals = cast(list[object], payload["signals"])
    evidence = cast(list[object], payload["evidence"])
    opportunities = cast(list[object], payload["opportunities"])
    ranked_opportunities = cast(list[object], payload["ranked_opportunities"])
    errors = cast(list[object], payload["errors"])
    metadata = cast(dict[str, object], payload["metadata"])

    return {
        "run_id": str(payload["run_id"]),
        "source_items": [SourceItem.model_validate(item) for item in source_items],
        "events": [Event.model_validate(item) for item in events],
        "signals": [Signal.model_validate(item) for item in signals],
        "evidence": [Evidence.model_validate(item) for item in evidence],
        "opportunities": [Opportunity.model_validate(item) for item in opportunities],
        "ranked_opportunities": [
            Opportunity.model_validate(item) for item in ranked_opportunities
        ],
        "errors": [str(error) for error in errors],
        "metadata": metadata,
    }
