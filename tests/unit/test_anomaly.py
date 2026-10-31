from decimal import Decimal

from anomaly.rules import detect
from metrics import check_statements, compute_metrics, values_from_rows
from parse.table import CellValue, StatementRow


def D(value: str) -> Decimal:
    return Decimal(value)


def _row(label: str, current: str | None, previous: str | None = None) -> StatementRow:
    cells = []
    if current is not None:
        cells.append(CellValue(current, D(current), "current", 10, (0, 0, 0, 0)))
    if previous is not None:
        cells.append(CellValue(previous, D(previous), "previous", 10, (0, 0, 0, 0)))
    return StatementRow(label=label, page=10, snippet=label, cells=tuple(cells), is_missing=not cells)


def _values():
    rows = {
        "income": [
            _row("营业总收入", "1000", "800"),
            _row("营业成本", "600", "500"),
            _row("销售费用", "50", "40"),
            _row("管理费用", "30", "20"),
            _row("财务费用", "20", "10"),
            _row("净利润", "100", "80"),
            _row("归属于母公司股东的净利润", "90", "70"),
            _row("少数股东损益", "10", "10"),
            _row("扣除非经常性损益后的净利润", "85", "60"),
        ],
        "balance": [
            _row("应收账款", "300", "150"),  # 增速 100% > 营收 25%
            _row("存货", "400", "250"),
            _row("商誉", "200", "200"),
            _row("短期借款", "200", "100"),
            _row("长期借款", "50", "40"),
            _row("应付债券", "30", "30"),
            _row("资产总计", "2000", "1800"),
            _row("负债合计", "1200", "1100"),
            _row("所有者权益合计", "800", "700"),
        ],
        "cashflow": [_row("经营活动产生的现金流量净额", "60", "90")],
    }
    return values_from_rows(rows)


def test_detects_cash_content_and_debt_rules():
    values = _values()
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    codes = {item.rule_code for item in detect(values, metrics, checks)}
    assert "cash_content_below_one" in codes
    assert "ocf_declining" in codes
    assert "debt_fast_growth" in codes


def test_detects_receivable_and_inventory_growth():
    values = _values()
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    codes = {item.rule_code for item in detect(values, metrics, checks)}
    assert "ar_growth_exceeds_revenue" in codes
    assert "inventory_growth_exceeds_revenue" in codes


def test_detects_goodwill_ratio_and_check_failure():
    values = _values()
    values["balance"]["total_liabilities"] = {"current": D("1100"), "previous": D("1100")}  # 人为制造不平
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    items = detect(values, metrics, checks)
    titles = {item.rule_code: item for item in items}

    assert "goodwill_ratio_high" in titles
    assert "check_balance_identity" in titles
    assert "仅陈列" not in titles["goodwill_ratio_high"].text
    assert "占净资产" in titles["goodwill_ratio_high"].text


def test_no_false_positive_on_healthy_company():
    rows = {
        "income": [
            _row("营业总收入", "1000", "900"),
            _row("营业成本", "500", "450"),
            _row("净利润", "200", "180"),
            _row("归属于母公司股东的净利润", "200", "180"),
            _row("少数股东损益", "0", "0"),
        ],
        "balance": [
            _row("应收账款", "100", "95"),
            _row("存货", "100", "95"),
            _row("商誉", "10", "10"),
            _row("资产总计", "2000", "1900"),
            _row("负债合计", "1000", "900"),
            _row("所有者权益合计", "1000", "1000"),
        ],
        "cashflow": [_row("经营活动产生的现金流量净额", "250", "200")],
    }
    values = values_from_rows(rows)
    metrics = {item.code: item for item in compute_metrics(values)}
    codes = {item.rule_code for item in detect(values, metrics, check_statements(values))}
    assert "cash_content_below_one" not in codes
    assert "ar_growth_exceeds_revenue" not in codes
