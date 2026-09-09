"""Tests for FastAPI sidecar."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pdf2muse.api import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_job_rejects_missing_pdf(client, tmp_path):
    response = client.post(
        "/jobs",
        json={"pdf_path": str(tmp_path / "missing.pdf")},
    )
    assert response.status_code == 400


def test_musicxml_endpoint_missing_job(client):
    response = client.get("/jobs/does-not-exist/musicxml")
    assert response.status_code == 404


def test_musicxml_endpoint_returns_bytes(tmp_path):
    from pdf2muse.api import JobRecord, JobStatus

    app = create_app()
    out = tmp_path / "out"
    out.mkdir()
    (out / "combined.musicxml").write_bytes(
        b'<?xml version="1.0"?><score-partwise version="3.1"/>'
    )
    app.state.jobs["job-ready"] = JobRecord(
        id="job-ready",
        status=JobStatus.COMPLETED,
        output_dir=out,
    )
    client = TestClient(app)
    response = client.get("/jobs/job-ready/musicxml")
    assert response.status_code == 200
    assert b"<score-partwise" in response.content

