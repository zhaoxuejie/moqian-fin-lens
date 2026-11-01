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
