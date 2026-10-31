from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from anomaly.rules import AnomalyItem
from metrics import MetricResult

ZERO = Decimal(0)


def _val(values: Mapping[str, dict[str, dict[str, Decimal]]], statement: str, code: str, period: str = "current"):
    return values.get(statement, {}).get(code, {}).get(period)


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _metric(metrics: Mapping[str, MetricResult], code: str) -> MetricResult | None:
    return metrics.get(code)


def build_charts(
    values: Mapping[str, dict[str, dict[str, Decimal]]],
    metrics: Mapping[str, MetricResult],
    periods: list[str],
) -> list[dict[str, object]]:
    """装配 V1～V7 图表数据；V8 由异常项接口提供。"""
    revenue = _val(values, "income", "revenue_total")
    deducted = _val(values, "income", "net_profit_deducted")
    ocf = _val(values, "cashflow", "ocf_net")
    cash_content = _metric(metrics, "cash_content")

    charts: list[dict[str, object]] = []

    charts.append(
        {
            "id": "v1",
            "title": "利润的含金量",
            "kind": "combo",
            "unit": "元",
            "x": periods,
            "series": [
                {"name": "营业收入", "type": "bar", "data": [_num(revenue)], "yAxisIndex": 0},
                {"name": "扣非净利润", "type": "line", "data": [_num(deducted)], "yAxisIndex": 1},
                {"name": "经营现金流", "type": "line", "data": [_num(ocf)], "yAxisIndex": 1},
            ],
            "meta": {
                "caliber": "营业总收入、扣非净利润取合并利润表；经营现金流取合并现金流量表",
                "sources": [],
                "missing": [name for name, value in (("营业收入", revenue), ("扣非净利润", deducted), ("经营现金流", ocf)) if value is None],
            },
        }
    )

    charts.append(
        {
            "id": "v2",
            "title": "现金含量",
            "kind": "combo",
            "unit": "倍",
            "x": periods,
            "series": [
                {"name": "经营现金流", "type": "bar", "data": [_num(ocf)], "yAxisIndex": 0},
                {
                    "name": "现金含量",
                    "type": "line",
                    "data": [None if cash_content is None else _num(cash_content.value)],
                    "yAxisIndex": 1,
                    "markLine": {"value": 1.0, "label": "1.0 警戒"},
                },
            ],
            "meta": {"caliber": "经营现金流 ÷ 净利润", "sources": [], "missing": [] if cash_content and cash_content.value is not None else ["现金含量"]},
        }
    )

    net_margin = _metric(metrics, "net_margin")
    assets = _val(values, "balance", "total_assets")
    equity = _val(values, "balance", "total_equity")
    turnover = None if not assets else (revenue / assets if revenue is not None else None)
    leverage = None if not equity else (assets / equity if assets is not None else None)
    charts.append(
        {
            "id": "v3",
            "title": "杜邦拆解",
            "kind": "mini-multiples",
            "unit": "%",
            "x": periods,
            "series": [
                {"name": "净利率", "type": "bar", "data": [None if not net_margin else _num(net_margin.value)]},
                {"name": "总资产周转率", "type": "bar", "data": [_num(turnover)], "unit": "次"},
                {"name": "权益乘数", "type": "bar", "data": [_num(leverage)], "unit": "倍"},
            ],
            "meta": {"caliber": "净利率 × 总资产周转率 × 权益乘数 = ROE", "sources": [], "missing": []},
        }
    )

    growth_series = []
    missing_growth = []
    for name, code in (("营收增速", "revenue_total"), ("应收增速", "accounts_receivable")):
        growth = _metric(metrics, "revenue_growth")
        if growth is None or growth.value is None:
            missing_growth.append(name)
        growth_series.append(
            {
                "name": name,
                "type": "line",
                "data": [None if not growth else _num(growth.value)],
            }
        )
    growth_series.append(
        {
            "name": "经营现金流增速",
            "type": "line",
            "data": [None],
        }
    )
    charts.append(
        {
            "id": "v4",
            "title": "增长质量：三速剪刀差",
            "kind": "lines",
            "unit": "%",
            "x": periods,
            "series": growth_series,
            "meta": {
                "caliber": "营收增速 vs 应收增速 vs 经营现金流增速",
                "sources": [],
                "missing": missing_growth + ["需要两期数据"],
            },
        }
    )

    expense = _metric(metrics, "expense_ratio")
    charts.append(
        {
            "id": "v5",
            "title": "费用结构",
            "kind": "bar",
            "unit": "%",
            "x": periods,
            "series": [
                {"name": "三费占收入比", "type": "bar", "data": [None if not expense else _num(expense.value)]}
            ],
            "meta": {"caliber": "销售 + 管理 + 财务费用 ÷ 营业总收入", "sources": [], "missing": [] if expense and expense.value is not None else ["三费占收入比"]},
        }
    )

    ratio_rows = []
    for name, code in (
        ("商誉", "goodwill"),
        ("应收账款", "accounts_receivable"),
        ("存货", "inventory"),
    ):
        value = _val(values, "balance", code)
        ratio_rows.append(
            {
                "name": name,
                "type": "bar",
                "data": [None if value is None or not equity else _num(value / equity * 100)],
            }
        )
    ratio_rows.append(
        {
            "name": "有息负债",
            "type": "bar",
            "data": [None],
        }
    )
    charts.append(
        {
            "id": "v6",
            "title": "资产结构",
            "kind": "grouped-bar",
            "unit": "%",
            "x": periods,
            "series": ratio_rows,
            "meta": {"caliber": "各科目 ÷ 所有者权益合计", "sources": [], "missing": []},
        }
    )

    investing = _val(values, "cashflow", "icf_net")
    financing = _val(values, "cashflow", "fcf_net")
    charts.append(
        {
            "id": "v7",
            "title": "现金流从哪来、到哪去",
            "kind": "grouped-bar",
            "unit": "元",
            "x": periods,
            "series": [
                {"name": "经营活动", "type": "bar", "data": [_num(ocf)]},
                {"name": "投资活动", "type": "bar", "data": [_num(investing)]},
                {"name": "筹资活动", "type": "bar", "data": [_num(financing)]},
            ],
            "meta": {"caliber": "三分类净额", "sources": [], "missing": []},
        }
    )

    return charts


def build_anomaly_payload(items: list[AnomalyItem]) -> list[dict[str, object]]:
    return [
        {
            "rule_code": item.rule_code,
            "title": item.title,
            "text": item.text,
            "evidence": item.evidence,
            "page_refs": item.page_refs,
        }
        for item in items
    ]
