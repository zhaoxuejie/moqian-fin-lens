from fastapi.testclient import TestClient

from app.main import create_app


def _client(settings, session):
    application = create_app(settings)
    application.state.sessions[session.session_id] = session
    return TestClient(application)


def test_dashboard_page_renders(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/s/s_test")
        charts = client.get("/s/s_test/charts")

    assert response.status_code == 200
    body = response.text
    assert "示例科技股份有限公司" in body
    assert "本期结论" in body
    assert "免责声明" in body
    assert charts.status_code == 200
    assert 'id="chart-c1"' in charts.text
    assert 'id="chart-c11"' in charts.text
    assert "盈利与增长" in charts.text
    assert "现金质量" in charts.text
    assert "风险与结构" in charts.text


def test_anomalies_live_on_statements_page(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        statements = client.get("/s/s_test/statements")
        charts = client.get("/s/s_test/charts")

    assert statements.status_code == 200
    assert 'id="anomaly"' in statements.text
    assert "异常项高亮" in statements.text
    assert "2024 年报本期与上期比较列" in statements.text
    assert 'id="anomaly"' not in charts.text


def test_session_detail_contract(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["session_id"] == "s_test"
    assert data["company_name"] == "示例科技股份有限公司"
    assert data["filing_count"] == 1
    assert data["filings"][0]["period"] == "2024"
    assert data["checks"]


def test_statements_endpoint_returns_three_tables(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/statements")
        only_income = client.get("/api/v1/sessions/s_test/statements?kind=income")

    assert response.status_code == 200
    kinds = [item["kind"] for item in response.json()["data"]["statements"]]
    assert kinds == ["income", "balance", "cashflow"]
    assert [item["kind"] for item in only_income.json()["data"]["statements"]] == ["income"]


def test_metrics_endpoint_returns_twenty(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/metrics")

    items = response.json()["data"]["metrics"]
    assert len(items) == 20
    assert {item["code"] for item in items} >= {"gross_margin", "roe", "cash_content"}


def test_charts_endpoint_returns_ten(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/charts")

    charts = response.json()["data"]["charts"]
    assert [chart["id"] for chart in charts] == [f"c{index}" for index in range(1, 12)]
    assert all(chart["x"] == ["2023（比较列）", "2024"] for chart in charts)
    assert all(series["unit"] for chart in charts for series in chart["series"])


def test_anomalies_endpoint(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/s_test/anomalies")

    items = response.json()["data"]["items"]
    assert isinstance(items, list)
    assert any(item["rule_code"] == "cash_content_below_one" for item in items)


def test_unknown_session_returns_40401(settings, dashboard_session):
    with _client(settings, dashboard_session) as client:
        response = client.get("/api/v1/sessions/nope")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 40401
    assert body["data"] is None
