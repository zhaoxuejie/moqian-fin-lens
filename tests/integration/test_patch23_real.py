"""TASK-023 在真实年报上的验收：千元单位、上交所写法、营业总收入回退。"""

from decimal import Decimal
from pathlib import Path

import pytest

from dashboard.session import build_filing

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval" / "pdf"
SMIC = EVAL_DIR / "688981_中芯国际" / "688981_中芯国际_2024年年度报告.pdf"
KINGSOFT = EVAL_DIR / "688111_金山办公" / "688111_金山办公_2025年年度报告.pdf"
HIKVISION = EVAL_DIR / "002415_海康威视" / "002415_海康威视_2024年年度报告.pdf"


def _build(path: Path, period: str):
    if not path.exists():
        pytest.skip("缺少评估集 PDF")
    return build_filing(path, period)


def test_thousand_yuan_report_is_scaled():
    filing = _build(SMIC, "2024")
    metrics = filing.metrics_by_code
    # 报表印的是 57,795,570（单位：千元）
    assert metrics["revenue"].value == Decimal("57795570000")
    # 扣非来自「主要会计数据」一节：2,645,419（千元）
    assert metrics["net_profit_deducted"].value == Decimal("2645419000")
    revenue_row = next(row for row in filing.rows["income"] if "营业收入" in row.label and row.cells)
    assert revenue_row.cells[0].raw == "57,795,570"


def test_sse_report_has_roe_and_no_skipped_checks():
    filing = _build(KINGSOFT, "2025")
    assert filing.metrics_by_code["roe"].value is not None
    statuses = {check.rule: check.status for check in filing.checks}
    assert statuses["balance_identity"] == "passed"
    assert statuses["equity_split"] == "passed"


def test_report_without_top_line_keeps_revenue_metrics():
    filing = _build(HIKVISION, "2024")
    metrics = filing.metrics_by_code
    for code in ("gross_margin", "net_margin", "ar_turnover_days", "expense_ratio", "revenue_growth"):
        assert metrics[code].value is not None, code
    assert metrics["revenue_total"].value is None
