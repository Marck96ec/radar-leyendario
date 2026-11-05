from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_llm_provider,
    get_run_repository,
    get_source_provider,
)
from app.main import app
from app.repositories.runs import SQLiteRunRepository


class EmptySourceProvider:
    async def fetch(self):
        return []


class EmptyLLMProvider:
    async def structured_completion(self, system_prompt, user_prompt, response_model):
        raise AssertionError("the empty workflow should not call the LLM")


def test_run_can_be_recovered_with_safe_retry_and_opportunity_routes(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    app.dependency_overrides.update(
        {
            get_llm_provider: EmptyLLMProvider,
            get_source_provider: EmptySourceProvider,
            get_run_repository: lambda: repository,
        }
    )
    run_id = uuid4()
    client = TestClient(app)
    try:
        first = client.post("/api/v1/radar/run", json={"run_id": str(run_id)})
        retry = client.post("/api/v1/radar/run", json={"run_id": str(run_id)})
        details = client.get(f"/api/v1/radar/runs/{run_id}")
        opportunities = client.get(
            f"/api/v1/radar/runs/{run_id}/opportunities"
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert retry.status_code == 200
    assert retry.json()["run_id"] == str(run_id)
    assert details.status_code == 200
    assert details.json()["execution_trace"][-1] == "rank_opportunities"
    assert opportunities.status_code == 200
    assert opportunities.json() == []


def test_run_id_input_is_validated() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/radar/run",
        json={"run_id": "not-a-uuid"},
    )
    assert response.status_code == 422
