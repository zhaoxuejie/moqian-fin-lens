from decimal import Decimal

import pytest

from anomaly.rules import detect
from dashboard.charts import build_chart_set, group_charts
from dashboard.session import FilingData
from metrics import check_statements, compute_metrics, pages_from_rows, values_from_rows
from parse.table import CellValue, StatementRow


def D(value: str) -> Decimal:
    return Decimal(value)


def _row(label: str, current: str, previous: str | None = None) -> StatementRow:
    cells = [CellValue(current, D(current), "current", 1, (0, 0, 0, 0))]
    if previous:
        cells.append(CellValue(previous, D(previous), "previous", 1, (0, 0, 0, 0)))
    return StatementRow(label=label, page=1, snippet=label, cells=tuple(cells), is_missing=False)


def _rows():
    return {
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
            _row("归属于母公司所有者权益合计", "760", "740"),
            _row("所有者权益合计", "800", "700"),
            _row("应收账款", "300", "150"),
            _row("存货", "400", "250"),
            _row("商誉", "50", "50"),
        ],
        "cashflow": [
            _row("经营活动产生的现金流量净额", "120", "90"),
            _row("购建固定资产、无形资产和其他长期资产支付的现金", "40", "40"),
        ],
    }


def _filing(rows=None, period: str = "2024") -> FilingData:
    rows = rows if rows is not None else _rows()
    values = values_from_rows(rows)
    metrics = compute_metrics(values)
    checks = check_statements(values)
    anomalies = detect(values, {item.code: item for item in metrics}, checks, pages_from_rows(rows))
    return FilingData(
        filing_id="f_01",
        period=period,
        pages=10,
        rows=rows,
        values=values,
        metrics=metrics,
        checks=checks,
        anomalies=anomalies,
    )


def _by_id(charts):
    return {chart["id"]: chart for chart in charts}


def test_build_chart_set_returns_eleven_charts():
    charts = build_chart_set([_filing()])
    assert [chart["id"] for chart in charts] == [f"c{index}" for index in range(1, 12)]
    for chart in charts:
        assert chart["group"] in {"盈利与增长", "现金质量", "风险与结构"}
        assert chart["title"]
        assert isinstance(chart["x"], list) and chart["x"]
        assert isinstance(chart["series"], list) and chart["series"]
        for series in chart["series"]:
            assert series["unit"] in {"元", "%", "倍", "次"}
            assert series["type"] in {"bar", "line"}


def test_chart_groups_keep_order():
    charts = build_chart_set([_filing()])
    groups = group_charts(charts)
    assert [group["title"] for group in groups] == ["盈利与增长", "现金质量", "风险与结构"]
    assert [len(group["charts"]) for group in groups] == [6, 2, 3]


def test_revenue_chart_is_first():
    charts = _by_id(build_chart_set([_filing()]))
    assert charts["c1"]["title"] == "营业总收入与增速"
    assert [series["name"] for series in charts["c1"]["series"]] == ["营业总收入", "营收增速"]
    assert charts["c1"]["series"][1]["unit"] == "%"
    assert charts["c1"]["series"][1]["data"][1] == pytest.approx(25.0, abs=0.01)


def test_single_period_uses_previous_column():
    charts = _by_id(build_chart_set([_filing()]))
    assert charts["c2"]["x"] == ["2023（比较列）", "2024"]
    growth = next(series for series in charts["c2"]["series"] if series["name"] == "扣非增速")
    assert growth["data"][0] is None
    assert growth["data"][1] == pytest.approx(41.67, abs=0.01)


def test_roe_and_turnover_first_point_is_empty():
    charts = _by_id(build_chart_set([_filing()]))
    roe = charts["c4"]["series"][0]
    assert roe["data"][0] is None
    assert roe["data"][1] == pytest.approx(12.0, abs=0.01)

    receivable = charts["c10"]["series"][0]
    assert receivable["data"][0] is None
    assert receivable["data"][1] == pytest.approx(1000 / 225, abs=0.01)


def test_free_cash_flow_is_derived():
    charts = _by_id(build_chart_set([_filing()]))
    fcf = next(series for series in charts["c7"]["series"] if series["name"] == "自由现金流")
    assert fcf["data"] == [pytest.approx(50.0), pytest.approx(80.0)]
    assert fcf["sign_colors"] is True


def test_free_cash_flow_missing_reports_capex():
    rows = _rows()
    rows["cashflow"] = [_row("经营活动产生的现金流量净额", "120", "90")]
    charts = _by_id(build_chart_set([_filing(rows)]))
    missing = charts["c7"]["meta"]["missing"]
    assert "自由现金流" in missing
    assert "购建长期资产支付的现金" in missing


def test_mark_lines_and_axes():
    charts = _by_id(build_chart_set([_filing()]))
    assert charts["c4"]["series"][0]["markLine"]["value"] == 15.0
    assert charts["c7"]["series"][2]["markLine"]["value"] == 1.0
    assert charts["c9"]["series"][0]["markLine"]["value"] == 60.0

    dupont = {series["name"]: series for series in charts["c5"]["series"]}
    assert dupont["净利率"]["yAxisIndex"] == 0
    assert dupont["总资产周转率"]["yAxisIndex"] == 1
    assert dupont["权益乘数"]["yAxisIndex"] == 1


def test_multi_period_axis_uses_years():
    charts = build_chart_set([_filing(period="2023"), _filing(period="2024")])
    assert charts[0]["x"] == ["2023", "2024"]
    for chart in charts:
        assert chart["x"] == ["2023", "2024"]


def test_missing_values_are_reported_not_zero():
    rows = _rows()
    rows["cashflow"] = []
    charts = _by_id(build_chart_set([_filing(rows)]))
    assert "经营现金流" in charts["c7"]["meta"]["missing"]
    assert charts["c7"]["series"][0]["data"] == [None, None]
