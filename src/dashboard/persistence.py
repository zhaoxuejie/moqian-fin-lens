"""会话快照序列化：把 SessionData 与 FilingData 与 JSON 互转。

v1.0 采用「快照落库」：filing 表存一份完整 JSON，页面与接口据此重建；
关系化拆表（entry / metric / check）留待后续版本，避免本卡阻塞上传闭环。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from anomaly.rules import AnomalyItem
from dashboard.session import FilingData, SessionData
from metrics import CheckResult, MetricResult
from parse.table import CellValue, StatementRow


def filing_to_dict(filing: FilingData) -> dict[str, Any]:
    return {
        "filing_id": filing.filing_id,
        "period": filing.period,
        "pages": filing.pages,
        "rows": {
            kind: [
                {
                    "label": row.label,
                    "page": row.page,
                    "snippet": row.snippet,
                    "is_missing": row.is_missing,
                    "cells": [
                        {
                            "raw": cell.raw,
                            "value": None if cell.value is None else str(cell.value),
                            "period": cell.period,
                            "page": cell.page,
                            "bbox": list(cell.bbox),
                        }
                        for cell in row.cells
                    ],
                }
                for row in rows
            ]
            for kind, rows in filing.rows.items()
        },
        "values": {
            statement: {
                code: {period: str(value) for period, value in periods.items()}
                for code, periods in codes.items()
            }
            for statement, codes in filing.values.items()
        },
        "metrics": [
            {
                "code": item.code,
                "label": item.label,
                "value": None if item.value is None else str(item.value),
                "unit": item.unit,
                "formula": item.formula,
                "missing_reason": item.missing_reason,
                "yoy": None if item.yoy is None else str(item.yoy),
                "yoy_unit": item.yoy_unit,
                "yoy_note": item.yoy_note,
            }
            for item in filing.metrics
        ],
        "checks": [
            {"rule": item.rule, "status": item.status, "diff": None if item.diff is None else str(item.diff), "detail": item.detail}
            for item in filing.checks
        ],
        "company_info": filing.company_info,
        "page_texts": {str(number): text for number, text in filing.page_texts.items()},
        "parsed_at": filing.parsed_at,
        "anomalies": [
            {
                "rule_code": item.rule_code,
                "title": item.title,
                "text": item.text,
                "evidence": item.evidence,
                "page_refs": item.page_refs,
            }
            for item in filing.anomalies
        ],
    }


def filing_from_dict(payload: dict[str, Any]) -> FilingData:
    rows: dict[str, list[StatementRow]] = {}
    for kind, items in payload.get("rows", {}).items():
        rows[kind] = [
            StatementRow(
                label=item["label"],
                page=item["page"],
                snippet=item["snippet"],
                cells=tuple(
                    CellValue(
                        raw=cell["raw"],
                        value=None if cell["value"] is None else Decimal(cell["value"]),
                        period=cell["period"],
                        page=cell["page"],
                        bbox=tuple(cell.get("bbox") or (0.0, 0.0, 0.0, 0.0)),
                    )
                    for cell in item.get("cells", [])
                ),
                is_missing=item.get("is_missing", False),
            )
            for item in items
        ]

    values: dict[str, dict[str, dict[str, Decimal]]] = {}
    for statement, codes in payload.get("values", {}).items():
        values[statement] = {
            code: {period: Decimal(text) for period, text in periods.items()}
            for code, periods in codes.items()
        }

    metrics = [
        MetricResult(
            code=item["code"],
            label=item["label"],
            value=None if item["value"] is None else Decimal(item["value"]),
            unit=item["unit"],
            formula=item["formula"],
            missing_reason=item.get("missing_reason"),
            yoy=None if item.get("yoy") is None else Decimal(item["yoy"]),
            yoy_unit=item.get("yoy_unit"),
            yoy_note=item.get("yoy_note"),
        )
        for item in payload.get("metrics", [])
    ]

    checks = [
        CheckResult(
            rule=item["rule"],
            status=item["status"],
            diff=None if item.get("diff") is None else Decimal(item["diff"]),
            detail=item.get("detail", ""),
        )
        for item in payload.get("checks", [])
    ]

    anomalies = [
        AnomalyItem(
            rule_code=item["rule_code"],
            title=item["title"],
            text=item["text"],
            evidence=item.get("evidence", []),
            page_refs=item.get("page_refs", []),
        )
        for item in payload.get("anomalies", [])
    ]

    return FilingData(
        filing_id=payload["filing_id"],
        period=payload["period"],
        pages=payload["pages"],
        rows=rows,
        values=values,
        metrics=metrics,
        checks=checks,
        anomalies=anomalies,
        company_info=payload.get("company_info", {}),
        page_texts={int(number): text for number, text in payload.get("page_texts", {}).items()},
        parsed_at=payload.get("parsed_at", ""),
    )


def session_to_json(session: SessionData) -> str:
    return json.dumps(
        {
            "session_id": session.session_id,
            "company_name": session.company_name,
            "stock_code": session.stock_code,
            "created_at": session.created_at,
            "filings": [filing_to_dict(filing) for filing in session.filings],
        },
        ensure_ascii=False,
    )


def session_from_json(text: str) -> SessionData:
    payload = json.loads(text)
    return SessionData(
        session_id=payload["session_id"],
        company_name=payload["company_name"],
        stock_code=payload.get("stock_code", ""),
        created_at=payload.get("created_at", ""),
        filings=[filing_from_dict(item) for item in payload.get("filings", [])],
    )
