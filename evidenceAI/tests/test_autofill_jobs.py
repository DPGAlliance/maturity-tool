import json
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from evidence_ai.db import Base, get_db_session
from evidence_ai.main import app
from evidence_ai.models import AutofillJob
from evidence_ai.worker import fail_stale_jobs, process_next_job


DIGIT_CORE_FIXTURE = Path(__file__).parent / "fixtures" / "digit_core_job.json"


@pytest.fixture
def database() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_session() -> Generator[Session, None, None]:
        session = sessions()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_session
    yield sessions
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_autofill_jobs_require_a_bearer_token(monkeypatch, database) -> None:
    monkeypatch.setenv("EVIDENCE_AI_API_KEY", "test-key")

    response = TestClient(app).post("/v1/mat/autofill-jobs", json={})

    assert response.status_code == 401


def test_create_and_poll_persistent_autofill_job(monkeypatch, database) -> None:
    monkeypatch.setenv("EVIDENCE_AI_API_KEY", "test-key")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "digit-core-001"}
    payload = json.loads(DIGIT_CORE_FIXTURE.read_text())

    created = client.post("/v1/mat/autofill-jobs", headers=headers, json=payload)
    repeated = client.post("/v1/mat/autofill-jobs", headers=headers, json=payload)

    assert created.status_code == 202
    assert repeated.json()["job_id"] == created.json()["job_id"]
    assert created.json()["status"] == "pending"

    conflicting = client.post(
        "/v1/mat/autofill-jobs",
        headers=headers,
        json={**payload, "product_name": "Different product"},
    )
    assert conflicting.status_code == 409

    polled = client.get(created.json()["status_url"], headers=headers)

    assert polled.status_code == 200
    assert polled.json()["product_id"] == "dev-digit-core"


def test_worker_completes_without_fabricating_suggestions(monkeypatch, database) -> None:
    monkeypatch.setenv("EVIDENCE_AI_API_KEY", "test-key")
    monkeypatch.delenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY_FILE", raising=False)
    monkeypatch.delenv("EVIDENCE_AI_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EVIDENCE_AI_OPENAI_API_KEY_FILE", raising=False)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-key"}
    payload = {
        "product_id": "dev-digit-core",
        "assessment_id": "dev-digit-core-assessment-001",
        "product_name": "DIGIT Core",
    }
    created = client.post("/v1/mat/autofill-jobs", headers=headers, json=payload)

    assert process_next_job(database) is True

    polled = client.get(created.json()["status_url"], headers=headers)
    assert polled.json()["status"] == "completed_with_warnings"
    assert polled.json()["result"] == {
        "sources": [],
        "evidence_suggestions": [],
        "capability_suggestions": [],
        "generation_outcome": "not_configured",
    }
    assert "OpenAI is not configured" in polled.json()["warnings"][-1]

    trace = client.get(f"/v1/mat/autofill-jobs/{created.json()['job_id']}/trace", headers=headers)
    assert trace.status_code == 200
    assert trace.json()["generation_attempts"][0]["outcome"] == "not_configured"
    action = trace.json()["investigation_actions"][0]
    assert action["action"] == "finish"
    assert action["requested"] == {"action": "finish"}
    assert action["outcome"] == "finished"


def test_worker_marks_stale_jobs_as_failed(database) -> None:
    with database() as session:
        job = AutofillJob(
            product_id="product",
            assessment_id="assessment",
            product_name="Product",
            request_fingerprint="x" * 64,
            status="running",
            stage="investigating",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=6),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    assert fail_stale_jobs(database) == 1

    with database() as session:
        job = session.get(AutofillJob, job_id)
        assert job and job.status == "failed"
        assert job.error_code == "worker_heartbeat_timeout"
