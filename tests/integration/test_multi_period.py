import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.config import Settings

BASE = Path(__file__).resolve().parents[1] / "eval" / "pdf"
PDF_2024 = BASE / "002230_科大讯飞" / "002230_科大讯飞_2024年年度报告.pdf"
PDF_2025 = BASE / "002230_科大讯飞" / "002230_科大讯飞_2025年年度报告.pdf"
OTHER = BASE / "002415_海康威视" / "002415_海康威视_2024年年度报告.pdf"


def _settings(tmp_path) -> Settings:
    return Settings(database_path=str(tmp_path / "app.db"), data_dir=str(tmp_path), _env_file=None)


def _wait(client, job_id, timeout=120):
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] in {"done", "failed"}:
            return job
        time.sleep(0.4)
    return job


def _upload(client, path: Path, session_id: str | None = None):
    data = {}
    if session_id:
        data["session_id"] = session_id
    response = client.post(
        "/api/v1/uploads",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data=data,
    )
    return response


@pytest.mark.skipif(not PDF_2024.exists() or not PDF_2025.exists(), reason="缺少评估集 PDF")
def test_multi_period_upload_and_charts(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        first = _upload(client, PDF_2024)
        assert first.status_code == 202
        session_id = first.json()["data"]["session_id"]
        job = _wait(client, first.json()["data"]["job"]["job_id"])
        assert job["state"] == "done", job

        second = _upload(client, PDF_2025, session_id=session_id)
        assert second.status_code == 202
        job = _wait(client, second.json()["data"]["job"]["job_id"])
        assert job["state"] == "done", job

        detail = client.get(f"/api/v1/sessions/{session_id}").json()["data"]
        charts = client.get(f"/api/v1/sessions/{session_id}/charts").json()["data"]["charts"]
        metrics = client.get(f"/api/v1/sessions/{session_id}/metrics").json()["data"]

    assert detail["filing_count"] == 2
    assert [item["period"] for item in detail["filings"]] == ["2024", "2025"]
    assert charts[0]["x"] == ["2024", "2025"]
    growth = next(chart for chart in charts if chart["id"] == "c6")
    assert any(value is not None for value in growth["series"][0]["data"])
    assert metrics["session_yoy"]


@pytest.mark.skipif(not PDF_2024.exists(), reason="缺少评估集 PDF")
def test_duplicate_period_is_rejected(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        first = _upload(client, PDF_2024)
        session_id = first.json()["data"]["session_id"]
        _wait(client, first.json()["data"]["job"]["job_id"])

        duplicate = _upload(client, PDF_2024, session_id=session_id)

    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == 40004
    assert duplicate.json()["detail"]["reason"] == "duplicate_period"


@pytest.mark.skipif(not PDF_2024.exists(), reason="缺少评估集 PDF")
def test_company_mismatch_is_rejected(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        first = _upload(client, PDF_2024)
        session_id = first.json()["data"]["session_id"]
        _wait(client, first.json()["data"]["job"]["job_id"])

        mismatch = _upload(client, OTHER, session_id=session_id)

    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == 40004


@pytest.mark.skipif(not PDF_2024.exists(), reason="缺少评估集 PDF")
def test_period_switcher_filters_statement(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        first = _upload(client, PDF_2024)
        session_id = first.json()["data"]["session_id"]
        _wait(client, first.json()["data"]["job"]["job_id"])

        page = client.get(f"/s/{session_id}?period=2024")

    assert page.status_code == 200
