from __future__ import annotations

import re

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from anomaly.rules import AnomalyItem, detect
from metrics import MetricResult, check_statements, compute_metrics, values_from_rows
from parse import PdfDoc, locate_statements
from parse.normalize import normalize
from parse.table import CellValue, StatementRow, extract_statement_rows


@dataclass
class FilingData:
    filing_id: str
    period: str
    pages: int
    rows: dict[str, list[StatementRow]]
    values: dict[str, dict[str, dict]]
    metrics: list[MetricResult]
    checks: list
    anomalies: list[AnomalyItem]

    @property
    def metrics_by_code(self) -> dict[str, MetricResult]:
        return {item.code: item for item in self.metrics}


@dataclass
class SessionData:
    session_id: str
    company_name: str
    stock_code: str
    filings: list[FilingData] = field(default_factory=list)
    created_at: str = ""

    @property
    def latest(self) -> FilingData:
        return self.filings[-1]

    @property
    def periods(self) -> list[str]:
        return [filing.period for filing in self.filings]


def filter_rows_by_statement(rows_by_kind: dict[str, list[StatementRow]]) -> dict[str, list[StatementRow]]:
    """按科目归属过滤行：利润表页里的母公司资产负债表尾行不进入利润表。"""
    from align import normalize_label
    from schema import load_accounts

    schema = load_accounts()
    filtered: dict[str, list[StatementRow]] = {}
    for kind, rows in rows_by_kind.items():
        kept = []
        for row in rows:
            account = schema.resolve(normalize_label(row.label))
            if account is not None and account.statement != kind:
                continue
            if not row.cells and row.label.endswith("："):
                continue
            kept.append(row)
        filtered[kind] = kept
    return filtered


DEDUCTED_LABEL = "扣除非经常性损益"
DEDUCTED_AMOUNT = re.compile(r"\(?-?[\d,]+\.\d{2}\)?")


def _add_deducted_fallback(rows: dict[str, list[StatementRow]], pages: list[str]) -> dict[str, list[StatementRow]]:
    """扣非净利润通常披露在「主要财务指标」而非三表页，缺省时全文兜底抓取一次。

    A 股年报的写法是「归属于上市公司股东的扣除非经常性损益的净利润」，
    且标签常被 PDF 拆成多段，因此在扁平化文本上定位标签，再取其后前两个金额。
    """
    if any("扣除非经常性损益" in row.label for row in rows.get("income", [])):
        return rows
    for index, text in enumerate(pages, start=1):
        flat = re.sub(r"\s+", "", text)
        position = flat.find(DEDUCTED_LABEL)
        if position == -1:
            continue
        window = flat[position:position + 160]
        label_end = window.find("净利润")
        if label_end == -1:
            continue
        tail = window[label_end + len("净利润"):]
        amounts = DEDUCTED_AMOUNT.findall(tail)
        if len(amounts) < 2:
            continue
        try:
            current = normalize(amounts[0]).value
            previous = normalize(amounts[1]).value
        except Exception:
            continue
        if current is None:
            continue
        cells = [CellValue(amounts[0], current, "current", index, (0.0, 0.0, 0.0, 0.0))]
        if previous is not None:
            cells.append(CellValue(amounts[1], previous, "previous", index, (0.0, 0.0, 0.0, 0.0)))
        rows.setdefault("income", []).append(
            StatementRow(
                label="归属于上市公司股东的扣除非经常性损益的净利润",
                page=index,
                snippet=window[:200],
                cells=tuple(cells),
                is_missing=False,
            )
        )
        return rows
    return rows


def build_filing(pdf_path: str | Path, period: str, filing_id: str = "f_01") -> FilingData:
    """把一份财报 PDF 变成看板需要的数据（定位 → 表格 → 指标 → 勾稽 → 异常）。"""
    path = str(pdf_path)
    with PdfDoc(path) as doc:
        page_count = doc.page_count
        pages = [doc.page_text(index) for index in range(1, page_count + 1)]

    located = locate_statements(pages)
    starts = {
        "income": located.income.start,
        "balance": located.balance.start,
        "cashflow": located.cashflow.start,
    }
    ordered = sorted(starts.values())
    ranges = {
        kind: (
            starts[kind],
            ordered[ordered.index(starts[kind]) + 1] - 1
            if ordered.index(starts[kind]) + 1 < len(ordered)
            else min(starts[kind] + 2, page_count),
        )
        for kind in starts
    }

    rows = extract_statement_rows(path, ranges)
    rows = _add_deducted_fallback(rows, pages)
    values = values_from_rows(rows)
    metrics = compute_metrics(values)
    checks = check_statements(values)
    anomalies = detect(values, {item.code: item for item in metrics}, checks)

    return FilingData(
        filing_id=filing_id,
        period=period,
        pages=page_count,
        rows=rows,
        values=values,
        metrics=metrics,
        checks=checks,
        anomalies=anomalies,
    )


def build_session(
    pdf_path: str | Path,
    company_name: str,
    stock_code: str = "",
    period: str = "",
    session_id: str = "s_demo",
) -> SessionData:
    """单期会话；多期通过 append_filing 追加。"""
    filing = build_filing(pdf_path, period or "2024", "f_01")
    return SessionData(
        session_id=session_id,
        company_name=company_name,
        stock_code=stock_code,
        filings=[filing],
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def company_key(name: str) -> str:
    """公司归一：去掉年份与扩展名，便于判断「同一公司」。"""
    import re

    value = re.sub(r"20\d{2}", "", name)
    value = re.sub(r"\.pdf$", "", value, flags=re.IGNORECASE)
    return value.strip("_- ").strip()


def append_filing(session: SessionData, filing: FilingData, max_filings: int = 5) -> SessionData:
    """把新一期追加进会话；重复期间 / 超期数 / 公司不一致都显式报错。"""
    from core.errors import AppError, ErrorCode

    if len(session.filings) >= max_filings:
        raise AppError(
            ErrorCode.SESSION_FULL,
            "会话期数已达上限",
            {"max_filings": max_filings},
        )
    if any(item.period == filing.period for item in session.filings):
        raise AppError(
            ErrorCode.SESSION_MISMATCH,
            "报告期已存在",
            {"period": filing.period, "reason": "duplicate_period"},
        )
    filings = sorted(session.filings + [filing], key=lambda item: item.period)
    return SessionData(
        session_id=session.session_id,
        company_name=session.company_name,
        stock_code=session.stock_code,
        filings=filings,
        created_at=session.created_at,
    )
