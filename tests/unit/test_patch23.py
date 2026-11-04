"""TASK-023 数值正确性修补：表头单位、上交所写法、营业总收入回退、有息负债、扣非兜底。"""

from decimal import Decimal

import pytest

from align import normalize_label
from dashboard.charts import build_chart_set
from dashboard.session import FilingData, _add_deducted_fallback
from metrics import METRIC_BY_CODE, check_statements, compute_metrics, values_from_rows
from parse.normalize import detect_unit
from parse.table import CellValue, StatementRow, _rows_from_table, statement_units


def D(value: str) -> Decimal:
    return Decimal(value)


def _row(label: str, current: str | None, previous: str | None = None) -> StatementRow:
    cells = []
    if current is not None:
        cells.append(CellValue(current, D(current), "current", 10, (0, 0, 0, 0)))
    if previous is not None:
        cells.append(CellValue(previous, D(previous), "previous", 10, (0, 0, 0, 0)))
    return StatementRow(label=label, page=10, snippet=label, cells=tuple(cells), is_missing=not cells)


# ---------- 1. 表头单位 ----------


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("单位：元 币种：人民币", "元"),
        ("单位：千元 币种：人民币", "千元"),
        ("单位:人民币千元", "千元"),
        ("单位： 万元", "万元"),
        ("编制单位：示例股份有限公司\n2025 年 12 月 31 日 单位：百万元", "百万元"),
        ("项目 附注 期末余额 期初余额", None),
    ],
)
def test_detect_unit(text, unit):
    assert detect_unit(text) == unit


def test_statement_units_reads_each_range_and_defaults_to_yuan():
    pages = ["合并资产负债表\n单位：千元", "续表", "合并利润表\n项目 本期 上期", "合并现金流量表"]
    units = statement_units(pages, {"balance": (1, 2), "income": (3, 3), "cashflow": (4, 4)})
    assert units == {"balance": "千元", "income": "元", "cashflow": "元"}


def test_rows_from_table_applies_unit_but_keeps_raw_text():
    table = [
        ["项目", "附注", "2025 年", "2024 年"],
        ["营业收入", "七、1", "57,795,570", "45,250,425"],
        ["营业成本", "七、1", "47,012,345", "36,123,456"],
        ["税金及附加", "", "12,345", "23,456"],
    ]
    rows = _rows_from_table(table, 120, "千元")
    revenue = rows[0]
    assert revenue.cells[0].value == D("57795570000")
    assert revenue.cells[0].raw == "57,795,570"  # 单年报表展示原文，不受换算影响


# ---------- 2. 上交所写法 ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.归属于母公司股东的净利润（净亏损以“-”号填列）", "归属于母公司股东的净利润"),
        ("2.少数股东损益（净亏损以“-”号填\n列）", "少数股东损益"),
        ("五、净利润（净亏损以“－”号填列）", "五、净利润"),
        ("所有者权益（或股东权益）合计", "所有者权益（或股东权益）合计"),
        ("其中：营业收入", "营业收入"),
    ],
)
def test_normalize_label_strips_numbering_and_fill_note(raw, expected):
    assert normalize_label(raw) == expected


def test_sse_labels_feed_roe_and_checks():
    rows = {
        "income": [
            _row("一、营业总收入", "1000", "800"),
            _row("五、净利润（净亏损以“－”号填列）", "100", "80"),
            _row("1.归属于母公司股东的净利润（净亏损以“-”号填列）", "90", "70"),
            _row("2.少数股东损益（净亏损以“-”号填\n列）", "10", "10"),
        ],
        "balance": [
            _row("资产总计", "2000", "1800"),
            _row("负债合计", "1200", "1100"),
            _row("归属于母公司所有者权益（或股东权益）合计", "760", "740"),
            _row("所有者权益（或股东权益）合计", "800", "700"),
        ],
        "cashflow": [],
    }
    values = values_from_rows(rows)
    metrics = {item.code: item for item in compute_metrics(values)}
    assert metrics["roe"].value == D("12")
    statuses = {check.rule: check.status for check in check_statements(values)}
    assert statuses["balance_identity"] == "passed"
    assert statuses["equity_split"] == "passed"


# ---------- 3. 营业总收入回退 ----------


def _no_top_line_rows():
    return {
        "income": [
            _row("一、营业收入", "1000", "800"),
            _row("减：营业成本", "600", "500"),
            _row("销售费用", "50", "40"),
            _row("管理费用", "30", "20"),
            _row("财务费用", "20", "10"),
            _row("净利润", "100", "80"),
        ],
        "balance": [_row("应收账款", "300", "150")],
        "cashflow": [],
    }


def test_metrics_fall_back_to_revenue_when_top_line_is_absent():
    metrics = {item.code: item for item in compute_metrics(values_from_rows(_no_top_line_rows()))}
    assert metrics["gross_margin"].value == D("40")
    assert metrics["net_margin"].value == D("10")
    assert metrics["expense_ratio"].value == D("10")
    assert metrics["revenue_growth"].value == D("25")
    assert metrics["ar_turnover_days"].value is not None
    # 营业总收入本身不冒充：原文没有这一行就是没有
    assert metrics["revenue_total"].value is None
    assert "未列示营业总收入时用营业收入" in metrics["gross_margin"].formula


def test_top_line_prefers_revenue_total_when_both_exist():
    rows = _no_top_line_rows()
    rows["income"].insert(0, _row("营业总收入", "1100", "900"))
    metrics = {item.code: item for item in compute_metrics(values_from_rows(rows))}
    assert metrics["gross_margin"].value == (D("1100") - D("600")) / D("1100") * 100


def test_charts_fall_back_to_revenue_too():
    rows = _no_top_line_rows()
    values = values_from_rows(rows)
    filing = FilingData("f_01", "2024", 10, rows, values, compute_metrics(values), [], [])
    revenue_chart = build_chart_set([filing])[0]
    assert revenue_chart["series"][0]["data"] == [800.0, 1000.0]


# ---------- 4. 有息负债 ----------


def test_interest_bearing_debt_needs_only_one_borrowing_line():
    rows = {"income": [], "balance": [_row("短期借款", "200", "100"), _row("长期借款", "50", "40")], "cashflow": []}
    metrics = {item.code: item for item in compute_metrics(values_from_rows(rows))}
    debt = metrics["interest_bearing_debt"]
    assert debt.value == D("250")
    assert debt.missing_reason is None
    # 同比按合计算：(250 - 140) / 140，而不是短期借款自己的 100%
    assert debt.yoy == (D("250") - D("140")) / D("140") * 100
    assert METRIC_BY_CODE["interest_bearing_debt"].any_of


def test_interest_bearing_debt_missing_only_when_all_lines_absent():
    rows = {"income": [], "balance": [_row("资产总计", "100", "90")], "cashflow": []}
    metrics = {item.code: item for item in compute_metrics(values_from_rows(rows))}
    assert metrics["interest_bearing_debt"].value is None
    assert metrics["interest_bearing_debt"].missing_reason.startswith("原文未披露")


# ---------- 5. 扣非净利润兜底（评测中追加）----------


def test_deducted_fallback_reads_integer_amounts_with_page_unit():
    page = (
        "单位：千元 币种：人民币\n"
        "归属于上市公司股东的净利润 3,698,665 4,822,814 -23.3 12,133,079\n"
        "归属于上市公司股东的扣除非经常性损益的净利润 2,645,419 3,269,518 -19.1 10,133,988\n"
    )
    rows = _add_deducted_fallback({"income": []}, ["封面", page])
    row = rows["income"][-1]
    assert [cell.value for cell in row.cells] == [D("2645419000"), D("3269518000")]
    assert row.page == 2


def test_deducted_fallback_uses_label_unit_and_skips_prose():
    pages = [
        "公司最近三个会计年度扣除非经常性损益前后净利润孰低者均为负值 □是 ☑否\n",
        "归属于上市公司股东的扣除非经常性\n损益的净利润（元） 188,137,288.93 118,061,711.15 59.36%\n",
    ]
    rows = _add_deducted_fallback({"income": []}, pages)
    row = rows["income"][-1]
    assert row.cells[0].value == D("188137288.93")
    assert row.page == 2
