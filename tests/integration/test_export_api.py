import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import create_app
from export.guard import assert_clean, find_banned


def _client(settings, session):
    application = create_app(settings)
    application.state.sessions[session.session_id] = session
    return TestClient(application)


def test_banned_words_are_detected():
    assert set(find_banned("建议买入该股票")) == {"买入", "建议买入"}
    with pytest.raises(ValueError):
        assert_clean("目标价 100 元")


def test_clean_text_passes():
    assert_clean("营收同比增长 20%，经营现金流下滑 10%。")


def test_trace_row(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/trace/row:income:0")

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["page"] == 10
    assert data["snippet"]
    assert data["entry_id"] == "row:income:0"


def test_trace_metric(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/trace/metric:gross_margin")

    data = response.json()["data"]
    assert data["page"] == 10
    assert "÷" in data["formula"]


def test_trace_unknown_entry(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/trace/row:income:999")

    assert response.status_code == 404
    assert response.json()["code"] == 40400


def test_markdown_export_download(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        created = client.post("/api/v1/sessions/s_test/exports", json={"kind": "markdown"})
        assert created.status_code == 200
        payload = created.json()["data"]
        assert payload["state"] == "ready"

        status = client.get(f"/api/v1/exports/{payload['export_id']}")
        assert status.json()["data"]["download_url"].endswith(payload["export_id"])

        downloaded = client.get(payload["download_url"])

    assert downloaded.status_code == 200
    text = downloaded.text
    assert "# 示例科技股份有限公司" in text
    assert "免责声明" in text
    assert "关键指标" in text
    assert "利润表" in text
    prose = "\n".join(line for line in text.splitlines() if not line.startswith("|"))
    assert find_banned(prose) == []


def test_xlsx_export_is_numeric(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        created = client.post("/api/v1/sessions/s_test/exports", json={"kind": "xlsx"})
        payload = created.json()["data"]
        downloaded = client.get(payload["download_url"])

    assert downloaded.status_code == 200
    workbook = load_workbook(io.BytesIO(downloaded.content))
    assert "关键指标" in workbook.sheetnames
    sheet = workbook["关键指标"]
    revenue_row = next(row for row in sheet.iter_rows(min_row=2) if row[0].value == "营业总收入")
    assert isinstance(revenue_row[1].value, (int, float))
    assert revenue_row[1].value == 1000.0


def test_export_unknown_kind_is_rejected(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.post("/api/v1/sessions/s_test/exports", json={"kind": "pdf"})

    assert response.status_code == 400
    assert response.json()["code"] == 40006
