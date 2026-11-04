from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from metrics import MetricResult

ZERO = Decimal(0)

# 每条规则引用的标准科目（报表, 科目）：页码从这些科目的取数行带出（接口契约：page_refs 至少一个）
RULE_ACCOUNTS: dict[str, tuple[tuple[str, str], ...]] = {
    "ar_growth_exceeds_revenue": (("balance", "accounts_receivable"), ("income", "revenue_total")),
    "cash_content_below_one": (("cashflow", "ocf_net"), ("income", "net_profit")),
    "ocf_declining": (("cashflow", "ocf_net"),),
    "gross_margin_declining": (("income", "revenue_total"), ("income", "cost_of_sales")),
    "debt_fast_growth": (
        ("balance", "short_term_borrowings"),
        ("balance", "long_term_borrowings"),
        ("balance", "bonds_payable"),
    ),
    "goodwill_ratio_high": (("balance", "goodwill"), ("balance", "total_equity")),
    "inventory_growth_exceeds_revenue": (("balance", "inventory"), ("income", "revenue_total")),
    "check_balance_identity": (
        ("balance", "total_assets"),
        ("balance", "total_liabilities"),
        ("balance", "total_equity"),
    ),
    "check_equity_split": (
        ("income", "net_profit"),
        ("income", "net_profit_attributable"),
        ("income", "minority_interest"),
    ),
    "check_net_profit_cashflow": (("income", "net_profit"), ("cashflow", "net_profit")),
}


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


def _margin(revenue: Decimal | None, cost: Decimal | None) -> Decimal | None:
    if revenue is None or cost is None or revenue == 0:
        return None
    return (revenue - cost) / revenue * 100


def detect(
    values: Mapping[str, dict[str, dict[str, Decimal]]],
    metrics: Mapping[str, MetricResult],
    checks: list,
    pages: Mapping[tuple[str, str], int],
) -> list[AnomalyItem]:
    """异常规则：只陈列数字之间的矛盾，不做评价。

    输入是单期年报的「本期 + 上期比较列」（PRD 4.6），所以只能做同比，不做「连续 N 年」。
    每条命中项都带证据科目的取数页码；找不到页码的项不返回（PRD R2、接口契约）。
    """
    items: list[AnomalyItem] = []

    def current(statement: str, code: str) -> Decimal | None:
        return values.get(statement, {}).get(code, {}).get("current")

    def previous(statement: str, code: str) -> Decimal | None:
        return values.get(statement, {}).get(code, {}).get("previous")

    def add(rule_code: str, title: str, text: str, evidence: list[dict[str, object]]) -> None:
        refs = sorted({pages[key] for key in RULE_ACCOUNTS[rule_code] if key in pages})
        if refs:
            items.append(AnomalyItem(rule_code, title, text, evidence, refs))

    revenue_growth = (
        metrics["revenue_growth"].value if "revenue_growth" in metrics else None
    )
    ar_growth = _growth(current("balance", "accounts_receivable"), previous("balance", "accounts_receivable"))
    if revenue_growth is not None and ar_growth is not None and ar_growth - revenue_growth >= 10:
        add(
            "ar_growth_exceeds_revenue",
            "应收账款增速显著高于营收增速",
            f"应收账款增速 {ar_growth:.1f}%，营收增速 {revenue_growth:.1f}%，差额 {ar_growth - revenue_growth:.1f} 个百分点。",
            [
                {"code": "accounts_receivable", "growth": f"{ar_growth:.2f}"},
                {"code": "revenue_total", "growth": f"{revenue_growth:.2f}"},
            ],
        )

    cash_content = metrics.get("cash_content")
    if cash_content and cash_content.value is not None and cash_content.value < 1:
        add(
            "cash_content_below_one",
            "经营现金流低于净利润",
            f"现金含量 {cash_content.value:.2f} 倍（经营现金流 ÷ 净利润），低于 1 倍。",
            [{"code": "cash_content", "value": f"{cash_content.value:.4f}"}],
        )

    ocf_current = current("cashflow", "ocf_net")
    ocf_previous = previous("cashflow", "ocf_net")
    if ocf_current is not None and ocf_previous is not None and ocf_current < ocf_previous:
        add(
            "ocf_declining",
            "经营活动现金流同比下降",
            f"经营现金流由上期 {ocf_previous:,.2f} 元降至本期 {ocf_current:,.2f} 元。",
            [{"code": "ocf_net", "current": f"{ocf_current}", "previous": f"{ocf_previous}"}],
        )

    margin_now = _margin(current("income", "revenue_total"), current("income", "cost_of_sales"))
    margin_prev = _margin(previous("income", "revenue_total"), previous("income", "cost_of_sales"))
    if margin_now is not None and margin_prev is not None and margin_prev - margin_now >= 1:
        add(
            "gross_margin_declining",
            "毛利率同比下降",
            f"毛利率由上期 {margin_prev:.1f}% 降至本期 {margin_now:.1f}%，下降 {margin_prev - margin_now:.1f} 个百分点。",
            [{"code": "gross_margin", "current": f"{margin_now:.2f}", "previous": f"{margin_prev:.2f}"}],
        )

    debt_codes = ("short_term_borrowings", "long_term_borrowings", "bonds_payable")
    debt_now = sum((current("balance", code) or ZERO for code in debt_codes), ZERO)
    debt_prev = sum((previous("balance", code) or ZERO for code in debt_codes), ZERO)
    debt_growth = _growth(debt_now, debt_prev)
    if debt_growth is not None and debt_growth >= 30:
        add(
            "debt_fast_growth",
            "有息负债快速上升",
            f"有息负债同比 +{debt_growth:.1f}%，本期 {debt_now:,.2f} 元。",
            [{"code": "interest_bearing_debt", "growth": f"{debt_growth:.2f}"}],
        )

    goodwill = current("balance", "goodwill")
    equity = current("balance", "total_equity")
    ratio = _pct(goodwill, equity) if goodwill is not None else None
    if ratio is not None and ratio >= 10:
        add(
            "goodwill_ratio_high",
            "商誉占净资产比例偏高",
            f"商誉 {goodwill:,.2f} 元，占净资产 {ratio:.1f}%。",
            [{"code": "goodwill", "value": f"{goodwill}", "ratio": f"{ratio:.2f}"}],
        )

    inventory_growth = _growth(current("balance", "inventory"), previous("balance", "inventory"))
    if revenue_growth is not None and inventory_growth is not None and inventory_growth - revenue_growth >= 10:
        add(
            "inventory_growth_exceeds_revenue",
            "存货增速高于营收增速",
            f"存货增速 {inventory_growth:.1f}%，营收增速 {revenue_growth:.1f}%。",
            [{"code": "inventory", "growth": f"{inventory_growth:.2f}"}],
        )

    for check in checks:
        if getattr(check, "status", "") == "failed" and f"check_{check.rule}" in RULE_ACCOUNTS:
            add(
                f"check_{check.rule}",
                "三表勾稽不通过",
                f"{check.detail} 差额 {check.diff}。",
                [{"rule": check.rule, "diff": str(check.diff)}],
            )

    return items
