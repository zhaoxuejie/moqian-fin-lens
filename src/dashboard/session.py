from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from anomaly.rules import AnomalyItem, detect
from metrics import MetricResult, check_statements, compute_metrics, values_from_rows
from parse import PdfDoc, locate_statements
from parse.table import StatementRow, extract_statement_rows


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
    """单期会话（多期会话由后续批次接入）。"""
    filing = build_filing(pdf_path, period or "2024", "f_01")
    return SessionData(
        session_id=session_id,
        company_name=company_name,
        stock_code=stock_code,
        filings=[filing],
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
