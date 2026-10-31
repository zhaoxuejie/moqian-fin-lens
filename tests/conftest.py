import pytest

from core.config import Settings


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        _env_file=None,
    )


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client

@pytest.fixture()
def dashboard_session():
    from decimal import Decimal

    from anomaly.rules import detect
    from dashboard.session import FilingData, SessionData
    from metrics import check_statements, compute_metrics, values_from_rows
    from parse.table import CellValue, StatementRow

    def row(label, current, previous=None):
        cells = [CellValue(current, Decimal(current), "current", 10, (0, 0, 0, 0))]
        if previous:
            cells.append(CellValue(previous, Decimal(previous), "previous", 10, (0, 0, 0, 0)))
        return StatementRow(label=label, page=10, snippet=label, cells=tuple(cells), is_missing=False)

    rows = {
        "income": [
            row("营业总收入", "1000", "800"),
            row("营业成本", "600", "500"),
            row("净利润", "100", "80"),
            row("归属于母公司股东的净利润", "90", "70"),
            row("扣除非经常性损益后的净利润", "85", "60"),
            row("销售费用", "50", "40"),
            row("管理费用", "30", "20"),
            row("财务费用", "20", "10"),
        ],
        "balance": [
            row("资产总计", "2000", "1800"),
            row("负债合计", "1200", "1100"),
            row("所有者权益合计", "800", "700"),
            row("应收账款", "300", "150"),
            row("存货", "400", "250"),
            row("商誉", "50", "50"),
        ],
        "cashflow": [row("经营活动产生的现金流量净额", "60", "90")],
    }
    values = values_from_rows(rows)
    metrics = compute_metrics(values)
    checks = check_statements(values)
    anomalies = detect(values, {item.code: item for item in metrics}, checks)
    filing = FilingData(
        filing_id="f_01",
        period="2024",
        pages=200,
        rows=rows,
        values=values,
        metrics=metrics,
        checks=checks,
        anomalies=anomalies,
    )
    return SessionData(
        session_id="s_test",
        company_name="示例科技股份有限公司",
        stock_code="300000.SZ",
        filings=[filing],
        created_at="2026-10-31T21:00:00+08:00",
    )
