from decimal import Decimal

from parse.table import (
    CellValue,
    StatementRow,
    _rows_from_table,
    build_rows,
    is_value_token,
    Word,
)


def test_value_token_boundaries():
    assert is_value_token("1,234,567.89")
    assert is_value_token("(114,817,493.16)")
    assert is_value_token("57,795,570")
    assert not is_value_token("2024")
    assert not is_value_token("12.3%")
    assert not is_value_token("七、1")
    assert not is_value_token("1,234)")


def test_rows_from_table_uses_two_value_columns():
    table = [
        ["", "项目", "", "2024年12月31日", "", "2023年12月31日"],
        ["", "货币资金", "", "3,387,380,425.36", "", "3,562,635,256.73"],
        ["", "应收账款", "", "14,666,453,043.92", "", "12,165,102,111.50"],
        ["", "商誉", "", "", "", ""],
    ]
    rows = _rows_from_table(table, page=114)
    assert len(rows) == 3
    assert rows[0].label == "货币资金"
    cells = {cell.period: cell.value for cell in rows[0].cells}
    assert cells["current"] == Decimal("3387380425.36")
    assert cells["previous"] == Decimal("3562635256.73")
    assert rows[2].is_missing is True
    assert rows[2].cells == ()


def test_rows_from_table_strips_note_suffix():
    table = [
        ["", "项目", "", "本年发生额", "", "上年发生额"],
        ["", "资产处置收益(损失)", "", "1,234,567.89", "", "2,234,567.89"],
    ]
    rows = _rows_from_table(table, page=161)
    assert rows[0].label == "资产处置收益"


def test_rows_from_table_without_header_uses_density():
    table = [
        ["", "租赁负债", "", "6,059,325.31", "", "64,962,842.49"],
        ["", "递延收益", "", "856,578,391.09", "", "415,933,000.81"],
    ]
    rows = _rows_from_table(table, page=119)
    assert len(rows) == 2
    assert {cell.period for cell in rows[0].cells} == {"current", "previous"}


def test_continuation_label_is_merged():
    table = [
        ["", "项目", "", "2024年度", "", "2023年度"],
        ["", "所有者权益（或股东", "", "", "", ""],
        ["", "益）合计", "", "6,537,942,083.99", "", "6,000,000,000.00"],
    ]
    rows = _rows_from_table(table, page=130)
    assert len(rows) == 1
    assert rows[0].label.startswith("所有者权益")
    assert rows[0].cells


def test_build_rows_from_words_keeps_page_and_snippet():
    words = [
        Word("货币资金", 40, 100, 120, 110),
        Word("3,387,380,425.36", 200, 100, 300, 110),
        Word("3,562,635,256.73", 330, 100, 430, 110),
    ]
    rows = build_rows(words, page=114)
    assert len(rows) == 1
    assert rows[0].page == 114
    assert "货币资金" in rows[0].snippet


def test_statement_row_dataclass_defaults():
    row = StatementRow(label="货币资金", page=1, snippet="", cells=(), is_missing=True)
    assert row.cells == ()
    assert row.is_missing is True
