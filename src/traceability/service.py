from __future__ import annotations

from typing import Any

from align import normalize_label
from core.errors import AppError, ErrorCode
from dashboard.session import SessionData, filter_rows_by_statement
from metrics.compute import _suffix_account
from metrics.registry import METRIC_BY_CODE
from schema import load_accounts

SCHEMA = load_accounts()
NUMBERING = __import__("re").compile(r"^[一二三四五六七八九十]+、")


def _resolve_row(row):
    label = NUMBERING.sub("", normalize_label(row.label))
    account = SCHEMA.resolve(label)
    if account is None:
        account = _suffix_account(label, SCHEMA)
    return account


def _row_trace(session: SessionData, entry_id: str, filing=None) -> dict[str, Any]:
    _, kind, index_text = entry_id.split(":", 2)
    filing = filing or session.latest
    rows = filter_rows_by_statement(filing.rows).get(kind, [])
    try:
        row = rows[int(index_text)]
    except (KeyError, IndexError, ValueError) as exc:
        raise AppError(ErrorCode.NOT_FOUND, "溯源记录不存在", {"entry_id": entry_id}) from exc
    cell = row.cells[0] if row.cells else None
    return {
        "entry_id": entry_id,
        "account_code": (_resolve_row(row).code if _resolve_row(row) else None),
        "label": row.label,
        "page": row.page,
        "snippet": row.snippet,
        "unit_note": "页面展示单位为元；原文单位见报表表头",
        "formula": None,
        "page_text": filing.page_texts.get(row.page, ""),
        "bbox": {"x0": cell.bbox[0], "y0": cell.bbox[1], "x1": cell.bbox[2], "y1": cell.bbox[3]} if cell else None,
    }


def _metric_trace(session: SessionData, entry_id: str, filing=None) -> dict[str, Any]:
    code = entry_id.split(":", 1)[1]
    filing = filing or session.latest
    metric = filing.metrics_by_code.get(code)
    if metric is None:
        raise AppError(ErrorCode.NOT_FOUND, "指标不存在", {"entry_id": entry_id})
    definition = METRIC_BY_CODE.get(code)
    requires = definition.requires if definition else ()
    page = None
    snippet = ""
    for account_code in requires:
        for kind, rows in filing.rows.items():
            for row in rows:
                account = _resolve_row(row)
                if account is not None and account.code == account_code:
                    page, snippet = row.page, row.snippet
                    break
            if page:
                break
        if page:
            break
    if page is None:
        raise AppError(ErrorCode.NOT_FOUND, "指标缺少原文出处", {"entry_id": entry_id})
    return {
        "entry_id": entry_id,
        "account_code": requires[0] if requires else None,
        "label": metric.label,
        "page": page,
        "snippet": snippet,
        "unit_note": "计算口径见 formula",
        "formula": metric.formula,
        "page_text": filing.page_texts.get(page, ""),
        "bbox": None,
    }


def trace_entry(session: SessionData, entry_id: str, filing=None) -> dict[str, Any]:
    if entry_id.startswith("row:"):
        return _row_trace(session, entry_id, filing)
    if entry_id.startswith("metric:"):
        return _metric_trace(session, entry_id, filing)
    raise AppError(ErrorCode.NOT_FOUND, "未知的溯源类型", {"entry_id": entry_id})
