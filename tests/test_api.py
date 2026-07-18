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
