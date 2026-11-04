import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.config import Settings

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval" / "pdf"
EVAL_PDF = EVAL_DIR / "002230_科大讯飞" / "002230_科大讯飞_2024年年度报告.pdf"


def _client(tmp_path) -> TestClient:
    settings = Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        max_upload_mb=5,
        max_pages=10,
        _env_file=None,
    )
    return TestClient(create_app(settings))


def test_upload_rejects_non_pdf(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json()["code"] == 40001


def test_upload_rejects_too_many_pages(tmp_path):
    if not EVAL_PDF.exists():
        pytest.skip("缺少评估集 PDF")
    settings = Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        max_upload_mb=50,
        max_pages=10,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("big.pdf", EVAL_PDF.read_bytes(), "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["code"] == 40003


def test_upload_rejects_oversize(tmp_path):
    with _client(tmp_path) as client:
        payload = b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024)
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("big.pdf", payload, "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["code"] == 40002


def test_job_not_found(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/api/v1/jobs/j_nope")

    assert response.status_code == 404
    assert response.json()["code"] == 40402


def test_upload_and_parse_to_dashboard(tmp_path):
    if not EVAL_PDF.exists():
        pytest.skip("缺少评估集 PDF")
    settings = Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        max_pages=400,
        _env_file=None,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        created = client.post(
            "/api/v1/uploads",
            files={"file": (EVAL_PDF.name, EVAL_PDF.read_bytes(), "application/pdf")},
        )
        assert created.status_code == 202
        payload = created.json()["data"]
        job_id = payload["job"]["job_id"]
        session_id = payload["session_id"]

        deadline = time.time() + 90
        job = {}
        while time.time() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if job["state"] in {"done", "failed"}:
                break
            time.sleep(0.5)

        assert job["state"] == "done", job
        page = client.get(f"/s/{session_id}")
        assert page.status_code == 200
        charts = client.get(f"/api/v1/sessions/{session_id}/charts").json()["data"]["charts"]
        assert len(charts) == 11
        run_log = tmp_path / "logs" / "runs.jsonl"
        assert run_log.exists()
        assert json.loads(run_log.read_text(encoding="utf-8").splitlines()[-1])["ok"] is True

def test_upload_rate_limited_after_ten(tmp_path):
    with _client(tmp_path) as client:
        statuses = []
        for _ in range(11):
            response = client.post(
                "/api/v1/uploads",
                files={"file": ("x.txt", b"not a pdf", "text/plain")},
            )
            statuses.append(response.status_code)

    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429

def test_home_page_supports_multi_file(tmp_path):
    with _client(tmp_path) as client:
        page = client.get("/")

    assert "dropzone" in page.text
    assert "progressbar" in page.text
    assert "多份年报" in page.text


def test_dashboard_has_continue_upload(settings, dashboard_session):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings)
    app.state.sessions[dashboard_session.session_id] = dashboard_session
    with TestClient(app) as client:
        page = client.get(f"/s/{dashboard_session.session_id}")

    assert page.status_code == 200
    assert "继续上传同一公司其他年报" in page.text
    assert 'id="continue-upload"' in page.text
    assert 'class="nav"' in page.text
    assert "company-head" in page.text
    assert "本期结论" in page.text
    assert 'id="company-toggle"' in page.text
    assert "外文名称" in page.text
    assert "本期报告" in page.text
    assert "公司全称" in page.text
    assert "全部指标" in page.text

def test_dashboard_pages_render(settings, dashboard_session):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings)
    app.state.sessions[dashboard_session.session_id] = dashboard_session
    pages = [
        ("/s/s_test", "本期结论"),
        ("/s/s_test/statements", "异常项高亮"),
        ("/s/s_test/compare", "跨年对比台"),
        ("/s/s_test/charts", "财务视图"),
    ]
    with TestClient(app) as client:
        for path, marker in pages:
            response = client.get(path)
            assert response.status_code == 200, path
            assert marker in response.text, (path, marker)


def _wait_job(client, job_id, timeout=120):
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    return job


def test_identity_comes_from_text_not_filename(tmp_path):
    """评估集年报一律改名为「年报.pdf」上传：公司简称、证券代码、年度都应从正文识别。"""
    pdfs = sorted(EVAL_DIR.rglob("*年度报告.pdf"))
    if not pdfs:
        pytest.skip("缺少评估集 PDF")
    settings = Settings(database_path=str(tmp_path / "app.db"), data_dir=str(tmp_path), max_pages=400, _env_file=None)
    with TestClient(create_app(settings)) as client:
        pending = []
        for pdf in pdfs:
            code, name, title = pdf.stem.split("_")
            created = client.post(
                "/api/v1/uploads",
                files={"file": ("年报.pdf", pdf.read_bytes(), "application/pdf")},
            )
            assert created.status_code == 202, created.json()
            data = created.json()["data"]
            assert data["filing"]["period"] == title[:4], pdf.name
            assert data["filing"]["report_type"] == "annual"
            pending.append((data["session_id"], data["job"]["job_id"], code, name))

        for session_id, job_id, code, name in pending:
            assert _wait_job(client, job_id, timeout=300)["state"] == "done"
            detail = client.get(f"/api/v1/sessions/{session_id}").json()["data"]
            assert (detail["stock_code"], detail["company_name"]) == (code, name)


def test_semi_annual_report_is_rejected(tmp_path, monkeypatch):
    if not EVAL_PDF.exists():
        pytest.skip("缺少评估集 PDF")
    import app.main as main_module
    from parse.identity import ReportIdentity

    monkeypatch.setattr(main_module, "identify_report", lambda pages: ReportIdentity("002230", "科大讯飞", "2025", "semi"))
    settings = Settings(database_path=str(tmp_path / "app.db"), data_dir=str(tmp_path), max_pages=400, _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("年报.pdf", EVAL_PDF.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["code"] == 42203
        assert client.app.state.jobs.jobs == {}
    assert not list((tmp_path / "tmp").glob("*.pdf"))
