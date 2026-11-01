from fastapi.testclient import TestClient

from evidence_ai.main import app


def test_autofill_jobs_require_a_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_API_KEY", "test-key")

    response = TestClient(app).post("/v1/mat/autofill-jobs", json={})

    assert response.status_code == 401


def test_create_and_poll_autofill_job(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_API_KEY", "test-key")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "digit-core-001"}
    payload = {
        "product_id": "dev-digit-core",
        "assessment_id": "dev-digit-core-assessment-001",
        "product_name": "DIGIT Core",
        "context": {
            "website_url": "https://core.digit.org",
            "repository_url": "https://github.com/egovernments/Digit-Core",
        },
    }

    created = client.post("/v1/mat/autofill-jobs", headers=headers, json=payload)
    repeated = client.post("/v1/mat/autofill-jobs", headers=headers, json=payload)

    assert created.status_code == 202
    assert repeated.json()["job_id"] == created.json()["job_id"]
    assert created.json()["status"] == "pending"
    assert created.json()["stage"] == "queued"

    polled = client.get(created.json()["status_url"], headers=headers)

    assert polled.status_code == 200
    assert polled.json()["product_id"] == "dev-digit-core"
