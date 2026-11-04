from decimal import Decimal

import pytest

from anomaly.rules import RULE_ACCOUNTS, detect
from metrics import check_statements, compute_metrics, pages_from_rows, values_from_rows
from parse.table import CellValue, StatementRow


def D(value: str) -> Decimal:
    return Decimal(value)


PAGES = {"income": 42, "balance": 40, "cashflow": 45}


def _row(label: str, current: str | None, previous: str | None = None, page: int = 10) -> StatementRow:
    cells = []
    if current is not None:
        cells.append(CellValue(current, D(current), "current", page, (0, 0, 0, 0)))
    if previous is not None:
        cells.append(CellValue(previous, D(previous), "previous", page, (0, 0, 0, 0)))
    return StatementRow(label=label, page=page, snippet=label, cells=tuple(cells), is_missing=not cells)


def _paged(rows):
    """按报表给行打上不同页码，便于断言异常项页码来自证据科目。"""
    return {
        kind: [
            StatementRow(row.label, PAGES[kind], row.snippet, row.cells, row.is_missing)
            for row in items
        ]
        for kind, items in rows.items()
    }


def _run(rows, mutate=None):
    rows = _paged(rows)
    values = values_from_rows(rows)
    if mutate:
        mutate(values)
    metrics = {item.code: item for item in compute_metrics(values)}
    return detect(values, metrics, check_statements(values), pages_from_rows(rows))


def _rows():
    return {
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


def _values():
    return values_from_rows(_rows())


def test_detects_cash_content_and_debt_rules():
    values = _values()
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    codes = {item.rule_code for item in detect(values, metrics, checks, pages_from_rows(_rows()))}
    assert "cash_content_below_one" in codes
    assert "ocf_declining" in codes
    assert "debt_fast_growth" in codes


def test_detects_receivable_and_inventory_growth():
    values = _values()
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    codes = {item.rule_code for item in detect(values, metrics, checks, pages_from_rows(_rows()))}
    assert "ar_growth_exceeds_revenue" in codes
    assert "inventory_growth_exceeds_revenue" in codes


def test_detects_goodwill_ratio_and_check_failure():
    values = _values()
    values["balance"]["total_liabilities"] = {"current": D("1100"), "previous": D("1100")}  # 人为制造不平
    metrics = {item.code: item for item in compute_metrics(values)}
    checks = check_statements(values)
    items = detect(values, metrics, checks, pages_from_rows(_rows()))
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
    codes = {item.rule_code for item in detect(values, metrics, check_statements(values), pages_from_rows(rows))}
    assert "cash_content_below_one" not in codes
    assert "ar_growth_exceeds_revenue" not in codes


def _healthy_rows():
    return {
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
            _row("短期借款", "100", "100"),
            _row("资产总计", "2000", "1900"),
            _row("负债合计", "1000", "900"),
            _row("所有者权益合计", "1000", "1000"),
        ],
        "cashflow": [_row("经营活动产生的现金流量净额", "250", "200")],
    }


def _set(statement, code, current, previous=None):
    def mutate(values):
        periods = {"current": D(current)}
        if previous is not None:
            periods["previous"] = D(previous)
        values.setdefault(statement, {})[code] = periods
    return mutate


# 8 条规则各一组「命中」与「未命中」的构造：命中改一个科目，未命中用健康样本
HITS = {
    "ar_growth_exceeds_revenue": _set("balance", "accounts_receivable", "150", "95"),
    "cash_content_below_one": _set("cashflow", "ocf_net", "100", "90"),
    "ocf_declining": _set("cashflow", "ocf_net", "210", "250"),
    "gross_margin_declining": _set("income", "cost_of_sales", "530", "450"),
    "debt_fast_growth": _set("balance", "short_term_borrowings", "200", "100"),
    "goodwill_ratio_high": _set("balance", "goodwill", "150", "150"),
    "inventory_growth_exceeds_revenue": _set("balance", "inventory", "150", "95"),
    "check_balance_identity": _set("balance", "total_liabilities", "900", "900"),
}


def test_rule_set_has_eight_rules():
    assert len(HITS) == 8
    assert set(HITS) <= set(RULE_ACCOUNTS)


@pytest.mark.parametrize("rule_code", sorted(HITS))
def test_each_rule_hits_with_page_refs(rule_code):
    items = {item.rule_code: item for item in _run(_healthy_rows(), HITS[rule_code])}
    assert rule_code in items
    assert items[rule_code].page_refs, "命中项必须带页码"
    assert set(items[rule_code].page_refs) <= set(PAGES.values())


@pytest.mark.parametrize("rule_code", sorted(HITS))
def test_each_rule_misses_on_healthy_sample(rule_code):
    assert rule_code not in {item.rule_code for item in _run(_healthy_rows())}


def test_page_refs_come_from_evidence_accounts():
    items = {item.rule_code: item for item in _run(_rows())}
    assert items["ocf_declining"].page_refs == [PAGES["cashflow"]]
    assert items["ar_growth_exceeds_revenue"].page_refs == sorted({PAGES["balance"], PAGES["income"]})


def test_items_without_page_are_dropped():
    values = _values()
    metrics = {item.code: item for item in compute_metrics(values)}
    assert detect(values, metrics, check_statements(values), {}) == []


def test_gross_margin_small_drop_is_not_flagged():
    # 50.0% → 49.5%：下降不足 1 个百分点
    items = _run(_healthy_rows(), _set("income", "cost_of_sales", "505", "450"))
    assert "gross_margin_declining" not in {item.rule_code for item in items}
