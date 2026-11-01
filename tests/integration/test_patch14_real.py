from pathlib import Path

import pytest

from dashboard.session import build_filing

PDF_DIR = Path(__file__).resolve().parents[1] / "eval" / "pdf"


def _pdf(company: str, year: str) -> Path:
    matches = list((PDF_DIR / company).glob(f"*{year}*.pdf"))
    if not matches:
        pytest.skip(f"缺少评估集 PDF：{company} {year}")
    return matches[0]


def test_deducted_profit_is_extracted_from_main_indicators():
    filing = build_filing(_pdf("002230_科大讯飞", "2024"), "2024")
    metric = next(item for item in filing.metrics if item.code == "net_profit_deducted")
    assert metric.value is not None
    assert metric.value > 0


def test_inventory_uses_consolidated_row_not_parent():
    filing = build_filing(_pdf("688111_金山办公", "2024"), "2024")
    value = filing.values["balance"]["inventory"]["current"]
    # 合并报表存货 802,036.62；母公司存货 79,594.31
    assert value > 700000

def test_statements_keep_consolidated_only():
    from dashboard.session import filter_rows_by_statement
    from dashboard.session import build_filing

    filing = build_filing(_pdf("002230_科大讯飞", "2024"), "2024")
    rows = filter_rows_by_statement(filing.rows)

    balance_labels = [row.label for row in rows["balance"]]
    income_labels = [row.label for row in rows["income"]]

    assert "负债和所有者权益总计" in balance_labels or "负债和所有者权益（或股东权益）总计" in balance_labels
    assert income_labels[-1].startswith("（二）稀释每股收益")
    assert any("六、其他综合收益的税后净额" in label for label in income_labels)

def test_first_balance_row_recovered():
    from dashboard.session import build_filing, filter_rows_by_statement

    filing = build_filing(_pdf("002230_科大讯飞", "2024"), "2024")
    rows = filter_rows_by_statement(filing.rows)["balance"]

    head = rows[0]
    assert head.label == "货币资金"
    assert head.page == 114
    assert head.cells[0].raw == "3,387,380,425.36"
    assert head.cells[1].raw == "3,562,635,256.73"
