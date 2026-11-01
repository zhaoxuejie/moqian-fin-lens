import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from core.config import Settings
from store.repo import SessionRepository, cleanup_temp_files


def _app(settings):
    return create_app(settings)


def _settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        _env_file=None,
    )


def test_session_survives_restart(tmp_path, dashboard_session):
    settings = _settings(tmp_path)
    first = _app(settings)
    first.state.repo.save(dashboard_session)
    first.state.sessions[dashboard_session.session_id] = dashboard_session

    second = _app(settings)
    with TestClient(second) as client:
        page = client.get(f"/s/{dashboard_session.session_id}")
        metrics = client.get(f"/api/v1/sessions/{dashboard_session.session_id}/metrics")

    assert page.status_code == 200
    assert "示例科技股份有限公司" in page.text
    assert len(metrics.json()["data"]["metrics"]) == 20


def test_snapshot_roundtrip_preserves_values(tmp_path, dashboard_session):
    repo = SessionRepository(_app(_settings(tmp_path)).state.db)
    repo.save(dashboard_session)
    restored = repo.load(dashboard_session.session_id)

    assert restored is not None
    assert restored.company_name == dashboard_session.company_name
    original = {item.code: item.value for item in dashboard_session.latest.metrics}
    loaded = {item.code: item.value for item in restored.latest.metrics}
    assert original == loaded
    assert restored.latest.pages == dashboard_session.latest.pages


def test_delete_session_removes_data_and_keeps_others(tmp_path, dashboard_session):
    settings = _settings(tmp_path)
    app = _app(settings)
    app.state.repo.save(dashboard_session)
    app.state.sessions[dashboard_session.session_id] = dashboard_session

    other = dashboard_session
    other_session = type(other)(
        session_id="s_other",
        company_name="另一家公司",
        stock_code="000001.SZ",
        filings=other.filings,
        created_at=other.created_at,
    )
    app.state.repo.save(other_session)
    app.state.sessions[other_session.session_id] = other_session

    with TestClient(app) as client:
        deleted = client.delete(f"/api/v1/sessions/{dashboard_session.session_id}")
        gone = client.get(f"/s/{dashboard_session.session_id}")
        kept = client.get("/api/v1/sessions/s_other")

    assert deleted.status_code == 200
    assert gone.status_code == 404
    assert kept.status_code == 200
    assert app.state.repo.count_filings(dashboard_session.session_id) == 0


def test_cleanup_removes_old_temp_files(tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    old = tmp / "old.pdf"
    fresh = tmp / "fresh.pdf"
    old.write_bytes(b"%PDF-1.4")
    fresh.write_bytes(b"%PDF-1.4")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))

    removed = cleanup_temp_files(tmp)

    assert removed == ["old.pdf"]
    assert not old.exists()
    assert fresh.exists()

def test_snapshot_preserves_company_info(tmp_path, dashboard_session):
    session = dashboard_session
    session.latest.company_info = {"全称": "示例科技股份有限公司", "办公地址": "示例市示例路 1 号"}
    app = _app(_settings(tmp_path))
    app.state.repo.save(session)

    restored = app.state.repo.load(session.session_id)

    assert restored is not None
    assert restored.latest.company_info["全称"] == "示例科技股份有限公司"
    assert restored.latest.company_info["办公地址"] == "示例市示例路 1 号"
