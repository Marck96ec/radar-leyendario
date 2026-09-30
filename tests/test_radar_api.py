from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
EXPECTED_TRACE = [
    "collect_sources",
    "normalize_sources",
    "cluster_events",
    "detect_signals",
    "validate_evidence",
    "generate_opportunities",
    "rank_opportunities",
]


def test_run_radar_executes_the_complete_workflow() -> None:
    response = client.post("/api/v1/radar/run")

    assert response.status_code == 200
    payload = response.json()
    UUID(payload["run_id"])
    assert payload["status"] == "completed"
    assert payload["sources"] == 0
    assert payload["events"] == 0
    assert payload["signals"] == 0
    assert payload["opportunities"] == 0
    assert payload["execution_trace"] == EXPECTED_TRACE


def test_health_endpoint_remains_unchanged() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "radar-leyendario",
    }
