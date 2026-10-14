from pydantic import BaseModel
from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_llm_provider,
    get_radar_run_repository,
    get_source_provider,
)
from app.infrastructure.database.radar_run_repository import InMemoryRadarRunRepository
from tests.test_radar_run_repository import build_state
from app.main import app


class EmptySourceProvider:
    async def fetch(self) -> list[object]:
        return []


class NoCallLLMProvider:
    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        raise AssertionError("GET must not invoke the LLM")


class FailingRepository:
    def save(self, run_result) -> None:
        raise RuntimeError("storage unavailable")

    def get_by_id(self, run_id: str):
        raise RuntimeError("storage unavailable")


def test_post_persists_and_get_returns_the_same_empty_run() -> None:
    repository = InMemoryRadarRunRepository()
    app.dependency_overrides[get_llm_provider] = lambda: NoCallLLMProvider()
    app.dependency_overrides[get_source_provider] = lambda: EmptySourceProvider()
    app.dependency_overrides[get_radar_run_repository] = lambda: repository
    try:
        client = TestClient(app)
        post_response = client.post("/api/v1/radar/run")
        run_id = post_response.json()["run_id"]
        get_response = client.get(f"/api/v1/radar/runs/{run_id}")
    finally:
        app.dependency_overrides.clear()

    assert post_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["run_id"] == run_id
    assert payload["summary"] == {
        "sources": 0,
        "events": 0,
        "signals": 0,
        "opportunities": 0,
    }
    assert payload["ranked_opportunities"] == []
    assert payload["top_opportunity"] is None


def test_get_rejects_invalid_uuid_and_missing_run() -> None:
    repository = InMemoryRadarRunRepository()
    app.dependency_overrides[get_radar_run_repository] = lambda: repository
    try:
        client = TestClient(app)
        invalid_response = client.get("/api/v1/radar/runs/not-a-uuid")
        missing_response = client.get(
            "/api/v1/radar/runs/00000000-0000-0000-0000-000000000000"
        )
    finally:
        app.dependency_overrides.clear()

    assert invalid_response.status_code == 422
    assert missing_response.status_code == 404


def test_get_uses_ranked_order_for_top_opportunity() -> None:
    repository = InMemoryRadarRunRepository()
    state = build_state()
    first = state["ranked_opportunities"][0].model_copy(
        update={"title": "First", "final_score": 91}
    )
    second = state["ranked_opportunities"][0].model_copy(
        update={"title": "Second", "final_score": 72}
    )
    state["ranked_opportunities"] = [first, second]
    repository.save(state)
    app.dependency_overrides[get_radar_run_repository] = lambda: repository
    try:
        response = TestClient(app).get(f"/api/v1/radar/runs/{state['run_id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload["ranked_opportunities"]] == [
        "First",
        "Second",
    ]
    assert payload["top_opportunity"]["title"] == "First"
    assert payload["top_opportunity"]["final_score"] == 91
    assert payload["signals"][0]["related_event_ids"] == [
        str(state["events"][0].id)
    ]


def test_post_does_not_report_success_when_storage_fails() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: NoCallLLMProvider()
    app.dependency_overrides[get_source_provider] = lambda: EmptySourceProvider()
    app.dependency_overrides[get_radar_run_repository] = FailingRepository
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/radar/run")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
