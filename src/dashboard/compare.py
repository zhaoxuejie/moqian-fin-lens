from __future__ import annotations

from decimal import Decimal

from align import normalize_label
from dashboard.session import SessionData
from schema import load_accounts

STATEMENT_ORDER = [
    ("balance", "资产负债表"),
    ("income", "利润表"),
    ("cashflow", "现金流量表"),
]


def _yoy(current: Decimal | None, previous: Decimal | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return float((current - previous) / abs(previous) * 100)


def build_comparison(session: SessionData) -> dict[str, object]:
    """跨年对比：按标准科目对齐，每年一列，并给出相对上一年的同比。"""
    schema = load_accounts()
    periods = [filing.period for filing in session.filings]
    statements: dict[str, object] = {}

    for kind, label in STATEMENT_ORDER:
        labels: dict[str, str] = {}
        for filing in session.filings:
            for row in filing.rows.get(kind, []):
                account = schema.resolve(normalize_label(row.label))
                if account is not None and account.code not in labels:
                    labels[account.code] = account.label

        # 行顺序跟随报表本身：取最近一期 values 的出现顺序，再补历史期
        codes: list[str] = []
        for filing in reversed(session.filings):
            for code in filing.values.get(kind, {}):
                if code not in codes:
                    codes.append(code)

        for code in codes:
            if code not in labels:
                account = schema.by_code.get(code)
                labels[code] = account.label if account is not None else code

        rows = []
        for code in codes:
            values: list[Decimal | None] = []
            for filing in session.filings:
                values.append(filing.values.get(kind, {}).get(code, {}).get("current"))
            if all(value is None for value in values):
                continue
            yoy: list[float | None] = []
            delta: list[Decimal | None] = []
            for index in range(len(values)):
                yoy.append(None if index == 0 else _yoy(values[index], values[index - 1]))
                delta.append(None if index == 0 or values[index] is None or values[index - 1] is None else values[index] - values[index - 1])
            rows.append(
                {
                    "code": code,
                    "label": labels.get(code, code),
                    "values": [None if value is None else str(value) for value in values],
                    "yoy": yoy,
                    "delta": [None if value is None else str(value) for value in delta],
                }
            )

        statements[kind] = {"kind": kind, "label": label, "rows": rows}

    return {"periods": periods, "statements": statements}
