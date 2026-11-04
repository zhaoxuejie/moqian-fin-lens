from __future__ import annotations

from dashboard.session import FilingData


def _metric(filing: FilingData, code: str):
    item = filing.metrics_by_code.get(code)
    return None if item is None or item.value is None else item.value


def _growth(filing: FilingData, statement: str, code: str):
    periods = filing.values.get(statement, {}).get(code, {})
    current, previous = periods.get("current"), periods.get("previous")
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


def build_summary(filing: FilingData) -> list[dict[str, str]]:
    """规则化结论摘要：只陈述数字与方向，不做投资建议。"""
    items: list[dict[str, str]] = []

    revenue_growth = _metric(filing, "revenue_growth")
    deducted = _metric(filing, "net_profit_deducted")
    deducted_growth = _metric(filing, "net_profit_growth")
    cash_content = _metric(filing, "cash_content")
    gross_margin = _metric(filing, "gross_margin")
    ar_growth = _growth(filing, "balance", "accounts_receivable")
    debt_ratio = _metric(filing, "debt_ratio")

    if revenue_growth is not None:
        positive = float(revenue_growth) >= 0
        items.append(
            {
                "tone": "up" if positive else "down",
                "text": f"营业总收入同比{'增长' if positive else '下降'} {abs(float(revenue_growth)):.1f}%。",
            }
        )

    if deducted is not None and deducted_growth is not None:
        positive = float(deducted_growth) >= 0
        items.append(
            {
                "tone": "up" if positive else "down",
                "text": f"扣非归母净利润同比{'增长' if deducted_growth >= 0 else '下降'} {abs(float(deducted_growth)):.1f}%。",
            }
        )

    if cash_content is not None:
        value = float(cash_content)
        if value >= 1:
            items.append({"tone": "info", "text": f"经营现金流 / 净利润 = {value:.2f}，不低于 1。"})
        else:
            items.append({"tone": "risk", "text": f"经营现金流 / 净利润 = {value:.2f}，低于 1。"})

    if ar_growth is not None and revenue_growth is not None:
        gap = float(ar_growth) - float(revenue_growth)
        if gap > 10:
            items.append(
                {
                    "tone": "risk",
                    "text": f"应收账款增速 {float(ar_growth):.1f}%，高于营收增速 {gap:.1f} 个百分点。",
                }
            )
        else:
            items.append(
                {
                    "tone": "info",
                    "text": f"应收账款增速 {float(ar_growth):.1f}%，营收增速 {float(revenue_growth):.1f}%。",
                }
            )

    if gross_margin is not None:
        items.append({"tone": "info", "text": f"毛利率 {float(gross_margin):.1f}%。"})

    if debt_ratio is not None:
        items.append({"tone": "info", "text": f"资产负债率 {float(debt_ratio):.1f}%。"})

    # 6 类事实各至多一行：营收、扣非、现金含量、应收、毛利率、资产负债率
    return items[:6]


def data_quality(filing: FilingData) -> dict[str, object]:
    checks = filing.checks or []
    passed = sum(1 for item in checks if item.status == "passed")
    skipped = sum(1 for item in checks if item.status == "skipped")
    failed = sum(1 for item in checks if item.status == "failed")

    undisclosed = 0
    total_rows = 0
    for rows in filing.rows.values():
        for row in rows:
            total_rows += 1
            if not row.cells or all(cell.value is None for cell in row.cells):
                undisclosed += 1

    return {
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
        "undisclosed": undisclosed,
        "total_rows": total_rows,
        "anomalies": len(filing.anomalies or []),
    }
