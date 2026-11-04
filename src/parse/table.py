from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from core.errors import AppError
from parse.normalize import detect_unit, normalize

NUMERIC = re.compile(r"^[\(（]?[-－—]?[\d,，]+(?:\.\d+)?[\)）]?$")
ROW_TOLERANCE = 4.0
COLUMN_TOLERANCE = 25.0
MIN_VALUE_WIDTH = 5  # 过滤附注列、页码、年份等短数字
HEADER_WORDS = {"项目", "附注", "单位", "币种", "编制单位", "单位：元"}
NOTE_SUFFIX = re.compile(r"[\(（](?:损失|[一二三四五六七八九十]+|\d+)[\)）]\d*$")
TITLE_TOKENS = {
    "合并利润表",
    "合并资产负债表",
    "合并现金流量表",
    "母公司利润表",
    "母公司资产负债表",
    "母公司现金流量表",
}

CURRENT_KEYS = ("期末", "本期", "本年", "本年年末", "本期发生额", "本年发生额", "本年金额", "期末余额")
PREVIOUS_KEYS = ("期初", "上期", "上年", "上年年末", "上期发生额", "上年发生额", "上年金额", "期初余额")


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class CellValue:
    raw: str
    value: Decimal | None
    period: str  # current | previous
    page: int
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class StatementRow:
    label: str
    page: int
    snippet: str
    cells: tuple[CellValue, ...]
    is_missing: bool


def is_value_token(text: str) -> bool:
    token = text.strip()
    if not NUMERIC.match(token):
        return False
    digits = re.sub(r"[^\d]", "", token)
    if len(digits) < MIN_VALUE_WIDTH and "," not in token and "." not in token:
        return False
    if ("(" in token) != (")" in token):
        return False
    return True


def _cluster_rows(words: Sequence[Word]) -> list[list[Word]]:
    rows: list[list[Word]] = []
    current: list[Word] = []
    previous_top: float | None = None
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        if previous_top is None or word.top - previous_top <= ROW_TOLERANCE:
            current.append(word)
        else:
            if current:
                rows.append(current)
            current = [word]
        previous_top = word.top
    if current:
        rows.append(current)
    return rows


def _column_centers(words: Sequence[Word]) -> list[float]:
    centers: list[float] = []
    for word in sorted(words, key=lambda item: item.x0):
        if not is_value_token(word.text):
            continue
        center = (word.x0 + word.x1) / 2
        if centers and abs(center - centers[-1]) <= COLUMN_TOLERANCE:
            centers[-1] = (centers[-1] + center) / 2
        else:
            centers.append(center)
    return centers


def _period_centers(words: Sequence[Word]) -> dict[str, float]:
    """从表头行读出「本期 / 上期」两列的 x 中心；读不到就返回空。"""
    for row_words in _cluster_rows(words):
        current = [word for word in row_words if any(key in word.text for key in CURRENT_KEYS)]
        previous = [word for word in row_words if any(key in word.text for key in PREVIOUS_KEYS)]
        if current and previous:
            return {
                "current": (current[0].x0 + current[0].x1) / 2,
                "previous": (previous[0].x0 + previous[0].x1) / 2,
            }
    return {}


def _split_regions(words: Sequence[Word]) -> list[list[Word]]:
    """同页多表切分（实验性，当前关闭，回归基线行为）。"""
    return [list(words)]
    boundaries: list[float] = []
    for word in words:
        if word.text in TITLE_TOKENS or word.text == "项目":
            boundaries.append(word.top)

    if not boundaries:
        return [list(words)]

    ordered = sorted({round(item, 1) for item in boundaries})
    regions: list[list[Word]] = []
    current: list[Word] = []
    boundary_index = 0
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        while boundary_index + 1 < len(ordered) and word.top >= ordered[boundary_index + 1] - 1:
            if current:
                regions.append(current)
            current = []
            boundary_index += 1
        current.append(word)
    if current:
        regions.append(current)
    return regions


def _assign_cells(
    numeric_words: Sequence[Word],
    centers: dict[str, float] | None,
    page: int,
    unit: str = "元",
) -> list[CellValue]:
    cells: list[CellValue] = []
    if centers:
        for period, center in centers.items():
            best = None
            for word in numeric_words:
                middle = (word.x0 + word.x1) / 2
                if abs(middle - center) <= 90:
                    if best is None or abs(middle - center) < abs((best.x0 + best.x1) / 2 - center):
                        best = word
            if best is not None:
                try:
                    parsed = normalize(best.text, unit)
                except AppError:
                    continue
                cells.append(
                    CellValue(
                        raw=best.text,
                        value=parsed.value,
                        period=period,
                        page=page,
                        bbox=(best.x0, best.top, best.x1, best.bottom),
                    )
                )
        if cells:
            return cells

    for order, word in enumerate(sorted(numeric_words, key=lambda item: item.x0)[:2]):
        try:
            parsed = normalize(word.text, unit)
        except AppError:
            continue
        cells.append(
            CellValue(
                raw=word.text,
                value=parsed.value,
                period="current" if order == 0 else "previous",
                page=page,
                bbox=(word.x0, word.top, word.x1, word.bottom),
            )
        )
    return cells


def build_rows(words: Sequence[Word], page: int, unit: str = "元") -> list[StatementRow]:
    """把单页的词块还原成带期间列的科目行（纯函数，便于单测）。"""
    result: list[StatementRow] = []

    for region in _split_regions(words):
        centers = {}
        fallback = _column_centers(region)
        if not centers and not fallback:
            continue
        left_edge = (min(list(centers.values()) + fallback[:1]) if (centers or fallback) else 0) - 20

        for row_words in _cluster_rows(region):
            label_parts = [
                word.text
                for word in row_words
                if word.x1 <= left_edge and not is_value_token(word.text)
            ]
            label = "".join(part.strip() for part in label_parts).strip("：: ")
            label = NOTE_SUFFIX.sub("", label).strip()
            if label in HEADER_WORDS or "。" in label or "，" in label or len(label) > 30:
                label = ""

            numeric_words = [word for word in row_words if is_value_token(word.text)]
            cells = _assign_cells(numeric_words, centers or None, page, unit)

            if not label and not cells:
                continue

            # 换行断词：上一行只有科目名，这一行是断词后半段或只有数字
            if cells and result and result[-1].cells == ():
                previous = result.pop()
                joined = previous.label + label
                if (not label) or label.startswith(("）", ")")) or len(label) <= 4:
                    snippet = (
                        previous.snippet
                        + " "
                        + " ".join(word.text for word in sorted(row_words, key=lambda item: item.x0))
                    ).strip()
                    result.append(
                        StatementRow(
                            label=joined if label else previous.label,
                            page=previous.page,
                            snippet=snippet[:200],
                            cells=tuple(cells),
                            is_missing=all(cell.value is None for cell in cells),
                        )
                    )
                    continue
                result.append(previous)

            snippet = " ".join(word.text for word in sorted(row_words, key=lambda item: item.x0))
            result.append(
                StatementRow(
                    label=label,
                    page=page,
                    snippet=snippet[:200],
                    cells=tuple(cells),
                    is_missing=not cells or all(cell.value is None for cell in cells),
                )
            )

    return result


def extract_words(pdf_path: str, pages: Iterable[int]) -> dict[int, list[Word]]:
    """用 pdfplumber 抽取指定页码（1 基）的词块与坐标。"""
    import pdfplumber

    result: dict[int, list[Word]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_number in pages:
            if page_number < 1 or page_number > len(pdf.pages):
                continue
            page = pdf.pages[page_number - 1]
            result[page_number] = [
                Word(
                    text=item["text"],
                    x0=float(item["x0"]),
                    top=float(item["top"]),
                    x1=float(item["x1"]),
                    bottom=float(item["bottom"]),
                )
                for item in page.extract_words(use_text_flow=False, keep_blank_chars=False)
            ]
    return result


def _rows_from_table(
    table: Sequence[Sequence[str | None]], page: int, unit: str = "元"
) -> list[StatementRow]:
    """把 pdfplumber 的一张表还原成科目行：表头定位期间列，左列取科目名。"""
    grid = [["" if cell is None else str(cell).strip() for cell in row] for row in table]
    if not grid:
        return []

    header_index = -1
    for index, row in enumerate(grid):
        if any("项目" in text for text in row):
            header_index = index
            break

    data = grid[header_index + 1:] if header_index >= 0 else grid
    width = max((len(row) for row in data), default=0)
    counts = [0] * width
    for row in data:
        for column, text in enumerate(row):
            if is_value_token(text):
                counts[column] += 1
    required = 2 if len(data) >= 3 else 1
    valuated = [column for column, count in enumerate(counts) if count >= required]
    if len(valuated) < 2:
        return []
    current_col, previous_col = valuated[-2], valuated[-1]
    left_columns = range(0, min(current_col, previous_col))
    rows: list[StatementRow] = []
    for row in grid[header_index + 1:]:
        label = ""
        for column in left_columns:
            text = row[column] if column < len(row) else ""
            if text and not is_value_token(text):
                label = text
                break
        if not label:
            label = "".join(
                row[column] for column in left_columns if column < len(row) and row[column]
            )

        cells: list[CellValue] = []
        for column, period in ((current_col, "current"), (previous_col, "previous")):
            text = row[column] if column < len(row) else ""
            if not is_value_token(text):
                continue
            try:
                parsed = normalize(text, unit)
            except AppError:
                continue
            cells.append(CellValue(text, parsed.value, period, page, (0.0, 0.0, 0.0, 0.0)))

        label = NOTE_SUFFIX.sub("", label).strip()
        if not label and not cells:
            continue
        if label in HEADER_WORDS:
            continue
        rows.append(
            StatementRow(
                label=label,
                page=page,
                snippet=" | ".join(text for text in row if text)[:200],
                cells=tuple(cells),
                is_missing=not cells or all(cell.value is None for cell in cells),
            )
        )

    merged: list[StatementRow] = []
    for row in rows:
        previous = merged[-1] if merged else None
        is_continuation = (
            row.cells
            and previous is not None
            and previous.cells == ()
            and (
                not row.label
                or row.label.startswith(("）", ")"))
                or (len(previous.label) >= 8 and len(row.label) <= 6)
            )
        )
        if is_continuation and previous is not None:
            merged.pop()
            merged.append(
                StatementRow(
                    label=previous.label + row.label,
                    page=previous.page,
                    snippet=previous.snippet + " " + row.snippet,
                    cells=row.cells,
                    is_missing=row.is_missing,
                )
            )
        else:
            merged.append(row)
    return merged


def statement_units(
    pages: Sequence[str],
    page_ranges: dict[str, tuple[int, int]],
) -> dict[str, str]:
    """每张表的金额单位：取页范围内第一处「单位：…」，读不到按元。

    单元格里的数字不带单位，单位只印在表头；不读这一行，千元报表的金额会小 1000 倍。
    """
    units: dict[str, str] = {}
    for kind, (start, end) in page_ranges.items():
        found = None
        for page_number in range(start, end + 1):
            if 1 <= page_number <= len(pages):
                found = detect_unit(pages[page_number - 1])
                if found:
                    break
        units[kind] = found or "元"
    return units


def extract_statement_rows(
    pdf_path: str,
    page_ranges: dict[str, tuple[int, int]],
    units: dict[str, str] | None = None,
) -> dict[str, list[StatementRow]]:
    """按三表页范围抽取行：pdfplumber 表格 API 为主，坐标聚类兜底；金额按各表表头单位换算成元。"""
    import pdfplumber

    units = units or {}
    result: dict[str, list[StatementRow]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for kind, (start, end) in page_ranges.items():
            unit = units.get(kind, "元")
            rows: list[StatementRow] = []
            for page_number in range(start, end + 1):
                if page_number < 1 or page_number > len(pdf.pages):
                    continue
                page = pdf.pages[page_number - 1]
                tables = page.extract_tables()
                for table in tables:
                    rows.extend(_rows_from_table(table, page_number, unit))
            if not rows:
                words = [
                    Word(item["text"], float(item["x0"]), float(item["top"]), float(item["x1"]), float(item["bottom"]))
                    for page_number in range(start, end + 1)
                    if 1 <= page_number <= len(pdf.pages)
                    for item in pdf.pages[page_number - 1].extract_words()
                ]
                rows = build_rows(words, start, unit)
            result[kind] = _merge_cross_page_rows(rows)
    return result


def _merge_cross_page_rows(rows: list[StatementRow]) -> list[StatementRow]:
    """跨页断行：上一行只有科目名、下一行只有数字时合并为一行。"""
    merged: list[StatementRow] = []
    for row in rows:
        if row.cells and not row.label and merged and not merged[-1].cells and merged[-1].label:
            previous = merged.pop()
            merged.append(
                StatementRow(
                    label=previous.label,
                    page=previous.page,
                    snippet=(previous.snippet + " " + row.snippet)[:200],
                    cells=row.cells,
                    is_missing=row.is_missing,
                )
            )
            continue
        merged.append(row)
    return merged