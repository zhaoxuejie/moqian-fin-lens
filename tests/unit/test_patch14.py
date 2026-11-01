from decimal import Decimal

from dashboard.session import _add_deducted_fallback
from metrics import values_from_rows
from parse.table import CellValue, StatementRow


def _row(label, current=None, previous=None, page=1):
    cells = []
    if current is not None:
        cells.append(CellValue(current, Decimal(current), "current", page, (0, 0, 0, 0)))
    if previous is not None:
        cells.append(CellValue(previous, Decimal(previous), "previous", page, (0, 0, 0, 0)))
    return StatementRow(label=label, page=page, snippet=label, cells=tuple(cells), is_missing=not cells)


def test_deducted_fallback_reads_main_indicators_page():
    pages = [
        "第二节 公司简介和主要财务指标",
        "扣除非经常性损益后的净利润 810,264,881.30 760,000,000.00",
    ]
    rows = {"income": [_row("营业总收入", "1000", "800")]}
    result = _add_deducted_fallback(rows, pages)

    labels = [row.label for row in result["income"]]
    assert any("扣除非经常性损益" in label for label in labels)
    values = values_from_rows(result)
    assert values["income"]["net_profit_deducted"]["current"] == Decimal("810264881.30")


def test_deducted_fallback_skipped_when_statement_has_it():
    rows = {"income": [_row("扣除非经常性损益后的净利润", "100", "90")]}
    pages = ["扣除非经常性损益后的净利润 999 888"]
    result = _add_deducted_fallback(rows, pages)
    assert len(result["income"]) == 1


def test_first_occurrence_wins_over_later_parent_company_row():
    # 合并报表在前、母公司报表在后：应取首次出现（合并）的值
    rows = {
        "balance": [
            _row("存货", "802036.62", "1412787.60", page=126),
            _row("存货", "79594.31", "160847.18", page=128),
        ]
    }
    values = values_from_rows(rows)
    assert values["balance"]["inventory"]["current"] == Decimal("802036.62")
