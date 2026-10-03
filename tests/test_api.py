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


def test_convert_request_accepts_header_lock_field():
    from pdf2muse.api import ConvertRequest

    req = ConvertRequest(pdf_path="/tmp/x.pdf", header_lock=True)
    assert req.header_lock is True
    req_default = ConvertRequest(pdf_path="/tmp/x.pdf")
    assert req_default.header_lock is False
    assert req_default.preview_first_page is False


def test_convert_request_accepts_preview_first_page():
    from pdf2muse.api import ConvertRequest

    req = ConvertRequest(pdf_path="/tmp/x.pdf", preview_first_page=True)
    assert req.preview_first_page is True


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
