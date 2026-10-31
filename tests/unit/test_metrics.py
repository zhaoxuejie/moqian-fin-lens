from decimal import Decimal

import pytest

from metrics import METRICS, check_statements, compute_metrics, values_from_rows
from parse.table import CellValue, StatementRow


def D(value: str) -> Decimal:
    return Decimal(value)


def _row(label: str, current: str | None, previous: str | None = None, page: int = 1) -> StatementRow:
    cells = []
    if current is not None:
        cells.append(CellValue(current, D(current), "current", page, (0, 0, 0, 0)))
    if previous is not None:
        cells.append(CellValue(previous, D(previous), "previous", page, (0, 0, 0, 0)))
    return StatementRow(label=label, page=page, snippet=label, cells=tuple(cells), is_missing=not cells)


def _full_values() -> dict:
    income = [
        _row("营业总收入", "1000", "800"),
        _row("营业收入", "900", "700"),
        _row("营业成本", "600", "500"),
        _row("销售费用", "50", "40"),
        _row("管理费用", "30", "20"),
        _row("财务费用", "20", "10"),
        _row("净利润", "100", "80"),
        _row("归属于母公司股东的净利润", "90", "70"),
        _row("少数股东损益", "10", "10"),
        _row("扣除非经常性损益后的净利润", "85", "60"),
    ]
    balance = [
        _row("应收账款", "200", "150"),
        _row("存货", "300", "250"),
        _row("商誉", "50", "50"),
        _row("短期借款", "100", "80"),
        _row("长期借款", "50", "40"),
        _row("应付债券", "30", "30"),
        _row("资产总计", "2000", "1800"),
        _row("负债合计", "1200", "1100"),
        _row("所有者权益合计", "800", "700"),
    ]
    cashflow = [_row("经营活动产生的现金流量净额", "120", "90")]
    return {"income": income, "balance": balance, "cashflow": cashflow}


def test_registry_has_twenty_metrics():
    assert len(METRICS) == 20
    codes = [metric.code for metric in METRICS]
    assert len(set(codes)) == 20


def test_values_from_rows_maps_labels_to_codes():
    values = values_from_rows(_full_values())
    assert values["income"]["revenue_total"]["current"] == D("1000")
    assert values["balance"]["total_assets"]["previous"] == D("1800")


def test_metrics_compute_expected_values():
    values = values_from_rows(_full_values())
    results = {item.code: item for item in compute_metrics(values)}

    assert results["gross_margin"].value == D("40")  # (1000-600)/1000*100
    assert results["net_margin"].value == D("10")  # 100/1000*100
    assert results["debt_ratio"].value == D("60")  # 1200/2000*100
    assert results["expense_ratio"].value == D("10")  # (50+30+20)/1000*100
    assert results["cash_content"].value == D("1.2")  # 120/100
    assert results["interest_bearing_debt"].value == D("180")  # 100+50+30
    assert results["roe"].value == D("12")  # 90 / avg(800,700)=750 *100
    assert abs(results["roa"].value - D("100") / D("1900") * 100) < D("0.000001")


def test_growth_metrics_use_previous_year():
    values = values_from_rows(_full_values())
    results = {item.code: item for item in compute_metrics(values)}
    assert results["revenue_growth"].value == D("25")  # (1000-800)/800
    assert abs(results["net_profit_growth"].value - (D("85") - D("60")) / D("60") * 100) < D("0.000001")


def test_missing_value_is_reported_not_zero():
    rows = {"income": [_row("营业总收入", "1000")], "balance": [], "cashflow": []}
    values = values_from_rows(rows)
    results = {item.code: item for item in compute_metrics(values)}
    gross = results["gross_margin"]
    assert gross.value is None
    assert gross.missing_reason and "cost_of_sales" in gross.missing_reason
    assert results["revenue_total"].value == D("1000")


def test_growth_with_zero_base_is_not_applicable():
    rows = {"income": [_row("营业总收入", "1000", "0")], "balance": [], "cashflow": []}
    values = values_from_rows(rows)
    growth = {item.code: item for item in compute_metrics(values)}["revenue_growth"]
    assert growth.value is None
    assert growth.missing_reason and "不适用" in growth.missing_reason


def test_balance_identity_passes():
    checks = {item.rule: item for item in check_statements(values_from_rows(_full_values()))}
    assert checks["balance_identity"].status == "passed"
    assert checks["equity_split"].status == "passed"
    assert checks["net_profit_cashflow"].status == "skipped"


def test_balance_identity_detects_tampering():
    rows = _full_values()
    rows["balance"][6] = _row("资产总计", "2100", "1800")  # 故意 +100
    checks = {item.rule: item for item in check_statements(values_from_rows(rows))}
    assert checks["balance_identity"].status == "failed"
    assert checks["balance_identity"].diff == D("100")


def test_equity_split_failure_is_detected():
    rows = _full_values()
    rows["income"][8] = _row("少数股东损益", "20", "10")  # 归母+少数 != 净利润
    checks = {item.rule: item for item in check_statements(values_from_rows(rows))}
    assert checks["equity_split"].status == "failed"
    assert checks["equity_split"].diff == D("-10")


def test_metrics_are_ordered_by_registry():
    values = values_from_rows(_full_values())
    results = compute_metrics(values)
    assert [item.code for item in results] == [metric.code for metric in METRICS]


def test_duplicate_rows_keep_first_value():
    income = [_row("营业总收入", "1000", "800"), _row("营业总收入", "999", "777")]
    values = values_from_rows({"income": income})
    assert values["income"]["revenue_total"]["current"] == D("1000")


def test_zero_cost_of_sales_gives_full_margin():
    rows = _full_values()
    rows["income"][2] = _row("营业成本", "0", "0")
    results = {item.code: item for item in compute_metrics(values_from_rows(rows))}
    assert results["gross_margin"].value == D("100")
