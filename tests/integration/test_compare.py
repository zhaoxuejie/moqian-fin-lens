from fastapi.testclient import TestClient

from app.main import create_app
from core.config import Settings


def _app(tmp_path):
    settings = Settings(database_path=str(tmp_path / "app.db"), data_dir=str(tmp_path), _env_file=None)
    return create_app(settings)


def test_compare_single_period(tmp_path, dashboard_session):
    app = _app(tmp_path)
    app.state.sessions[dashboard_session.session_id] = dashboard_session
    with TestClient(app) as client:
        response = client.get(f"/api/v1/sessions/{dashboard_session.session_id}/compare")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["periods"] == [dashboard_session.latest.period]
    for kind in ("balance", "income", "cashflow"):
        assert data["statements"][kind]["rows"], kind
        row = data["statements"][kind]["rows"][0]
        assert row["yoy"] == [None]
        assert len(row["values"]) == 1


def test_compare_multi_period_yoy(tmp_path, dashboard_session):
    from dataclasses import replace

    latest = dashboard_session.latest
    previous = replace(latest, period="2023", filing_id="f_prev")
    previous.values = {"balance": {"total_assets": {"current": __import__("decimal").Decimal("100")}}}
    latest.values = {"balance": {"total_assets": {"current": __import__("decimal").Decimal("125")}}}
    session = replace(dashboard_session, filings=[previous, latest])

    app = _app(tmp_path)
    app.state.sessions[session.session_id] = session
    with TestClient(app) as client:
        data = client.get(f"/api/v1/sessions/{session.session_id}/compare").json()["data"]

    row = next(item for item in data["statements"]["balance"]["rows"] if item["code"] == "total_assets")
    assert data["periods"] == ["2023", latest.period]
    assert row["values"] == ["100", "125"]
    assert round(row["yoy"][1], 2) == 25.0
    assert row["label"] == "资产总计"
