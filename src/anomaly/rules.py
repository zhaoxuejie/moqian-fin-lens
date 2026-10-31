from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from metrics import MetricResult

ZERO = Decimal(0)


@dataclass(frozen=True)
class AnomalyItem:
    rule_code: str
    title: str
    text: str
    evidence: list[dict[str, object]]
    page_refs: list[int]


def _growth(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


def _pct(value: Decimal, total: Decimal | None) -> Decimal | None:
    if total is None or total == 0:
        return None
    return value / total * 100


def detect(
    values: Mapping[str, dict[str, dict[str, Decimal]]],
    metrics: Mapping[str, MetricResult],
    checks: list,
) -> list[AnomalyItem]:
    """异常规则：只陈列数字之间的矛盾，不做评价。"""
    items: list[AnomalyItem] = []

    def current(statement: str, code: str) -> Decimal | None:
        return values.get(statement, {}).get(code, {}).get("current")

    def previous(statement: str, code: str) -> Decimal | None:
        return values.get(statement, {}).get(code, {}).get("previous")

    revenue_growth = (
        metrics["revenue_growth"].value if "revenue_growth" in metrics else None
    )
    ar_growth = _growth(current("balance", "accounts_receivable"), previous("balance", "accounts_receivable"))
    if revenue_growth is not None and ar_growth is not None and ar_growth - revenue_growth >= 10:
        items.append(
            AnomalyItem(
                "ar_growth_exceeds_revenue",
                "应收账款增速显著高于营收增速",
                f"应收账款增速 {ar_growth:.1f}%，营收增速 {revenue_growth:.1f}%，差额 {ar_growth - revenue_growth:.1f} 个百分点。",
                [
                    {"code": "accounts_receivable", "growth": f"{ar_growth:.2f}"},
                    {"code": "revenue_total", "growth": f"{revenue_growth:.2f}"},
                ],
                [],
            )
        )

    cash_content = metrics.get("cash_content")
    if cash_content and cash_content.value is not None and cash_content.value < 1:
        items.append(
            AnomalyItem(
                "cash_content_below_one",
                "经营现金流低于净利润",
                f"现金含量 {cash_content.value:.2f} 倍（经营现金流 ÷ 净利润），低于 1 倍。",
                [{"code": "cash_content", "value": f"{cash_content.value:.4f}"}],
                [],
            )
        )

    ocf_current = current("cashflow", "ocf_net")
    ocf_previous = previous("cashflow", "ocf_net")
    if ocf_current is not None and ocf_previous is not None and ocf_current < ocf_previous:
        items.append(
            AnomalyItem(
                "ocf_declining",
                "经营活动现金流同比下滑",
                f"经营现金流由上期 {ocf_previous:,.2f} 元降至本期 {ocf_current:,.2f} 元。",
                [
                    {"code": "ocf_net", "current": f"{ocf_current}", "previous": f"{ocf_previous}"}
                ],
                [],
            )
        )

    debt_growth = _growth(
        current("balance", "interest_bearing_debt"),
        previous("balance", "interest_bearing_debt"),
    )
    short = current("balance", "short_term_borrowings") or ZERO
    long = current("balance", "long_term_borrowings") or ZERO
    bonds = current("balance", "bonds_payable") or ZERO
    debt_now = short + long + bonds
    debt_prev = (previous("balance", "short_term_borrowings") or ZERO) + (
        previous("balance", "long_term_borrowings") or ZERO
    ) + (previous("balance", "bonds_payable") or ZERO)
    debt_growth = _growth(debt_now, debt_prev)
    if debt_growth is not None and debt_growth >= 30:
        items.append(
            AnomalyItem(
                "debt_fast_growth",
                "有息负债快速上升",
                f"有息负债同比 +{debt_growth:.1f}%，本期 {debt_now:,.2f} 元。",
                [{"code": "interest_bearing_debt", "growth": f"{debt_growth:.2f}"}],
                [],
            )
        )

    goodwill = current("balance", "goodwill")
    equity = current("balance", "total_equity")
    ratio = _pct(goodwill, equity) if goodwill is not None else None
    if ratio is not None and ratio >= 10:
        items.append(
            AnomalyItem(
                "goodwill_ratio_high",
                "商誉占净资产比例偏高",
                f"商誉 {goodwill:,.2f} 元，占净资产 {ratio:.1f}%。",
                [{"code": "goodwill", "value": f"{goodwill}", "ratio": f"{ratio:.2f}"}],
                [],
            )
        )

    inventory_growth = _growth(current("balance", "inventory"), previous("balance", "inventory"))
    if revenue_growth is not None and inventory_growth is not None and inventory_growth - revenue_growth >= 10:
        items.append(
            AnomalyItem(
                "inventory_growth_exceeds_revenue",
                "存货增速高于营收增速",
                f"存货增速 {inventory_growth:.1f}%，营收增速 {revenue_growth:.1f}%。",
                [{"code": "inventory", "growth": f"{inventory_growth:.2f}"}],
                [],
            )
        )

    for check in checks:
        if getattr(check, "status", "") == "failed":
            items.append(
                AnomalyItem(
                    f"check_{check.rule}",
                    "三表勾稽不通过",
                    f"{check.detail} 差额 {check.diff}。",
                    [{"rule": check.rule, "diff": str(check.diff)}],
                    [],
                )
            )

    return items
