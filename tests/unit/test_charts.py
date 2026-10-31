from decimal import Decimal

from dashboard.build import build_anomaly_payload, build_charts
from metrics import compute_metrics, values_from_rows
from parse.table import CellValue, StatementRow


def D(value: str) -> Decimal:
    return Decimal(value)


def _row(label: str, current: str, previous: str | None = None) -> StatementRow:
    cells = [CellValue(current, D(current), "current", 1, (0, 0, 0, 0))]
    if previous:
        cells.append(CellValue(previous, D(previous), "previous", 1, (0, 0, 0, 0)))
    return StatementRow(label=label, page=1, snippet=label, cells=tuple(cells), is_missing=False)


def _payload():
    rows = {
        "income": [
            _row("营业总收入", "1000", "800"),
            _row("营业成本", "600", "500"),
            _row("净利润", "100", "80"),
            _row("归属于母公司股东的净利润", "90", "70"),
            _row("扣除非经常性损益后的净利润", "85", "60"),
            _row("销售费用", "50", "40"),
            _row("管理费用", "30", "20"),
            _row("财务费用", "20", "10"),
        ],
        "balance": [
            _row("资产总计", "2000", "1800"),
            _row("负债合计", "1200", "1100"),
            _row("所有者权益合计", "800", "700"),
            _row("应收账款", "200", "150"),
            _row("存货", "300", "250"),
            _row("商誉", "50", "50"),
        ],
        "cashflow": [_row("经营活动产生的现金流量净额", "120", "90")],
    }
    values = values_from_rows(rows)
    metrics = {item.code: item for item in compute_metrics(values)}
    return values, metrics


def test_build_charts_returns_seven_payloads():
    values, metrics = _payload()
    charts = build_charts(values, metrics, ["2024"])
    assert [chart["id"] for chart in charts] == ["v1", "v2", "v3", "v4", "v5", "v6", "v7"]
    for chart in charts:
        assert chart["title"]
        assert chart["kind"] in {"combo", "mini-multiples", "lines", "bar", "grouped-bar"}
        assert chart["x"] == ["2024"]
        assert isinstance(chart["series"], list) and chart["series"]


def test_single_period_marks_growth_chart_missing():
    values, metrics = _payload()
    charts = {chart["id"]: chart for chart in build_charts(values, metrics, ["2024"])}
    assert "需要两期数据" in charts["v4"]["meta"]["missing"]


def test_missing_values_are_reported_not_zero():
    values, metrics = _payload()
    values["cashflow"] = {}
    charts = {chart["id"]: chart for chart in build_charts(values, metrics, ["2024"])}
    assert "经营现金流" in charts["v1"]["meta"]["missing"]
    assert charts["v1"]["series"][2]["data"] == [None]


def test_anomaly_payload_is_json_ready():
    values, metrics = _payload()
    items = build_anomaly_payload([])
    assert items == []
