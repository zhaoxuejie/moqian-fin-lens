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


def build_charts_multi(filings) -> list[dict[str, object]]:
    """多期图表：V1～V7 的 x 轴为会话内期间序列。"""
    periods = [filing.period for filing in filings]

    def values_at(filing, statement, code, period="current"):
        return filing.values.get(statement, {}).get(code, {}).get(period)

    def metric_at(filing, code):
        item = next((m for m in filing.metrics if m.code == code), None)
        return None if item is None or item.value is None else float(item.value)

    def series(name, kind, accessor, yaxis=None):
        entry = {"name": name, "type": kind, "data": [accessor(filing) for filing in filings]}
        if yaxis is not None:
            entry["yAxisIndex"] = yaxis
        return entry

    def num(value):
        return None if value is None else float(value)

    charts: list[dict[str, object]] = []
    charts.append(
        {
            "id": "v1",
            "title": "利润的含金量",
            "kind": "combo",
            "unit": "元",
            "x": periods,
            "series": [
                series("营业收入", "bar", lambda f: num(values_at(f, "income", "revenue_total")), 0),
                series("扣非净利润", "line", lambda f: num(values_at(f, "income", "net_profit_deducted")), 1),
                series("经营现金流", "line", lambda f: num(values_at(f, "cashflow", "ocf_net")), 1),
            ],
            "meta": {"caliber": "营业总收入 / 扣非净利润 / 经营现金流", "sources": [], "missing": []},
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
                series("经营现金流", "bar", lambda f: num(values_at(f, "cashflow", "ocf_net")), 0),
                series("现金含量", "line", lambda f: metric_at(f, "cash_content"), 1),
            ],
            "meta": {"caliber": "经营现金流 ÷ 净利润", "sources": [], "missing": []},
        }
    )
    charts.append(
        {
            "id": "v3",
            "title": "杜邦拆解",
            "kind": "mini-multiples",
            "unit": "%",
            "x": periods,
            "series": [
                series("净利率", "bar", lambda f: metric_at(f, "net_margin")),
                series(
                    "总资产周转率",
                    "bar",
                    lambda f: None
                    if not values_at(f, "balance", "total_assets")
                    else num(values_at(f, "income", "revenue_total") / values_at(f, "balance", "total_assets")),
                ),
                series(
                    "权益乘数",
                    "bar",
                    lambda f: None
                    if not values_at(f, "balance", "total_equity")
                    else num(values_at(f, "balance", "total_assets") / values_at(f, "balance", "total_equity")),
                ),
            ],
            "meta": {"caliber": "净利率 × 周转率 × 权益乘数", "sources": [], "missing": []},
        }
    )
    charts.append(
        {
            "id": "v4",
            "title": "增长质量：三速剪刀差",
            "kind": "lines",
            "unit": "%",
            "x": periods,
            "series": [
                series("营收增速", "line", lambda f: metric_at(f, "revenue_growth")),
                series("应收增速", "line", lambda f: _growth(f, "balance", "accounts_receivable")),
                series("经营现金流增速", "line", lambda f: _growth(f, "cashflow", "ocf_net")),
            ],
            "meta": {"caliber": "同比增速（PDF 比较列）", "sources": [], "missing": []},
        }
    )
    charts.append(
        {
            "id": "v5",
            "title": "费用结构",
            "kind": "bar",
            "unit": "%",
            "x": periods,
            "series": [series("三费占收入比", "bar", lambda f: metric_at(f, "expense_ratio"))],
            "meta": {"caliber": "三费 ÷ 营业总收入", "sources": [], "missing": []},
        }
    )

    def ratio(filing, code):
        value = values_at(filing, "balance", code)
        equity = values_at(filing, "balance", "total_equity")
        return None if value is None or not equity else num(value / equity * 100)

    charts.append(
        {
            "id": "v6",
            "title": "资产结构",
            "kind": "grouped-bar",
            "unit": "%",
            "x": periods,
            "series": [
                series("商誉", "bar", lambda f: ratio(f, "goodwill")),
                series("应收账款", "bar", lambda f: ratio(f, "accounts_receivable")),
                series("存货", "bar", lambda f: ratio(f, "inventory")),
            ],
            "meta": {"caliber": "各科目 ÷ 所有者权益合计", "sources": [], "missing": []},
        }
    )
    charts.append(
        {
            "id": "v7",
            "title": "现金流从哪来、到哪去",
            "kind": "grouped-bar",
            "unit": "元",
            "x": periods,
            "series": [
                series("经营活动", "bar", lambda f: num(values_at(f, "cashflow", "ocf_net"))),
                series("投资活动", "bar", lambda f: num(values_at(f, "cashflow", "icf_net"))),
                series("筹资活动", "bar", lambda f: num(values_at(f, "cashflow", "fcf_net"))),
            ],
            "meta": {"caliber": "三分类净额", "sources": [], "missing": []},
        }
    )
    return charts


def _growth(filing, statement: str, code: str) -> float | None:
    periods = filing.values.get(statement, {}).get(code, {})
    current = periods.get("current")
    previous = periods.get("previous")
    if current is None or previous is None or previous <= 0:
        return None
    return float((current - previous) / previous * 100)


def session_yoy(filings) -> dict[str, dict[str, object]]:
    """会话级同比：最新一期 vs 上一期；金额类给百分比，比率类给百分点。"""
    if len(filings) < 2:
        return {}
    latest, previous = filings[-1], filings[-2]
    prev_metrics = {item.code: item for item in previous.metrics}
    result: dict[str, dict[str, object]] = {}
    for item in latest.metrics:
        old = prev_metrics.get(item.code)
        if item.value is None or old is None or old.value is None:
            continue
        if item.unit == "%":
            result[item.code] = {"value": str(item.value - old.value), "unit": "pct"}
        elif old.value != 0 and old.value > 0:
            result[item.code] = {
                "value": str((item.value - old.value) / abs(old.value) * 100),
                "unit": "%",
            }
    return result

