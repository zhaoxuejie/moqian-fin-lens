"""图表数据装配：10 张多年趋势图，覆盖用户最看重的核心指标。

横轴为会话内各期年报；单期会话用报告「上期比较列」补成两个点。
依赖平均余额的指标（ROE、周转次数、杜邦三因子、增速）在「上期」栏为空，
因为需要更早一期数据，页面会标注。
"""

from __future__ import annotations

from typing import Callable

from dashboard.session import FilingData

Point = tuple[FilingData, str]
Accessor = Callable[[FilingData, str], float | None]

GROUP_PROFIT = "盈利与增长"
GROUP_CASH = "现金质量"
GROUP_RISK = "风险与结构"


def build_chart_set(filings: list[FilingData]) -> list[dict[str, object]]:
    """把会话内的各期财报装配成 10 张图表。"""
    if not filings:
        return []

    x, points = _axis(filings)

    return [
        _chart(
            "c1",
            GROUP_PROFIT,
            "营业总收入与增速",
            x,
            points,
            [
                _series("营业总收入", "bar", "元", lambda f, c: _raw(f, "income", "revenue_total", c)),
                _series(
                    "营收增速",
                    "line",
                    "%",
                    lambda f, c: None if c != "current" else _growth(f, "income", "revenue_total"),
                    yaxis=1,
                ),
            ],
            "营业总收入取合并利润表；增速按报告上期比较列计算",
        ),
        _chart(
            "c2",
            GROUP_PROFIT,
            "扣非净利润与增速",
            x,
            points,
            [
                _series(
                    "扣非净利润",
                    "bar",
                    "元",
                    lambda f, c: _raw(f, "income", "net_profit_deducted", c),
                    sign_colors=True,
                ),
                _series(
                    "扣非增速",
                    "line",
                    "%",
                    lambda f, c: None if c != "current" else _growth(f, "income", "net_profit_deducted"),
                    yaxis=1,
                ),
            ],
            "扣非净利润取合并利润表；增速按报告上期比较列计算；柱子在 0 线下方表示亏损",
        ),
        _chart(
            "c3",
            GROUP_PROFIT,
            "毛利率 / 净利率 / 三费占收入比",
            x,
            points,
            [
                _series("毛利率", "line", "%", _gross_margin),
                _series("净利率", "line", "%", _net_margin),
                _series("三费占收入比", "line", "%", _expense_ratio),
            ],
            "毛利率 =（营业总收入 − 营业成本）÷ 营业总收入；三费 = 销售 + 管理 + 财务费用",
        ),
        _chart(
            "c4",
            GROUP_PROFIT,
            "ROE",
            x,
            points,
            [
                _series("净资产收益率", "line", "%", _roe, mark_line=15.0, mark_label="15% 参考"),
            ],
            "加权平均净资产收益率 = 归母净利润 ÷ 平均所有者权益 × 100；上期栏需更早一期数据",
        ),
        _chart(
            "c5",
            GROUP_PROFIT,
            "杜邦拆解",
            x,
            points,
            [
                _series("净利率", "line", "%", _net_margin),
                _series("总资产周转率", "line", "次", _dupont_turnover, yaxis=1),
                _series("权益乘数", "line", "倍", _dupont_leverage, yaxis=1),
            ],
            "净利率 × 总资产周转率 × 权益乘数 ≈ ROE；周转率与权益乘数用平均余额",
            note=_dupont_check(filings[-1]),
        ),
        _chart(
            "c6",
            GROUP_PROFIT,
            "增长质量：三速剪刀差",
            x,
            points,
            [
                _series(
                    "营收增速",
                    "line",
                    "%",
                    lambda f, c: None if c != "current" else _growth(f, "income", "revenue_total"),
                ),
                _series(
                    "应收增速",
                    "line",
                    "%",
                    lambda f, c: None if c != "current" else _growth(f, "balance", "accounts_receivable"),
                ),
                _series(
                    "存货增速",
                    "line",
                    "%",
                    lambda f, c: None if c != "current" else _growth(f, "balance", "inventory"),
                ),
            ],
            "三条增速同尺度；应收或存货跑得比收入快，说明增长靠赊账或压货",
        ),
        _chart(
            "c7",
            GROUP_CASH,
            "经营现金流与自由现金流",
            x,
            points,
            [
                _series(
                    "经营现金流",
                    "bar",
                    "元",
                    lambda f, c: _raw(f, "cashflow", "ocf_net", c),
                    sign_colors=True,
                ),
                _series("自由现金流", "bar", "元", _free_cash_flow, sign_colors=True),
                _series(
                    "现金含量",
                    "line",
                    "倍",
                    _cash_content,
                    yaxis=1,
                    mark_line=1.0,
                    mark_label="1.0 警戒",
                ),
            ],
            "自由现金流 = 经营现金流 − 购建长期资产支付的现金；现金含量 = 经营现金流 ÷ 净利润",
            extra_missing=_capex_missing(filings),
        ),
        _chart(
            "c8",
            GROUP_CASH,
            "现金流三分类",
            x,
            points,
            [
                _series("经营活动", "bar", "元", lambda f, c: _raw(f, "cashflow", "ocf_net", c)),
                _series("投资活动", "bar", "元", lambda f, c: _raw(f, "cashflow", "icf_net", c)),
                _series("筹资活动", "bar", "元", lambda f, c: _raw(f, "cashflow", "fcf_net", c)),
            ],
            "三分类净额不堆叠，正值向上、负值向下；三项之和与现金及现金等价物净增加额的差异由汇率变动等造成",
        ),
        _chart(
            "c9",
            GROUP_RISK,
            "资产负债率",
            x,
            points,
            [
                _series(
                    "资产负债率",
                    "line",
                    "%",
                    _debt_ratio,
                    mark_line=60.0,
                    mark_label="60% 警戒",
                ),
            ],
            "资产负债率 = 负债合计 ÷ 资产总计 × 100；持续抬升时对照 ROE 看是否靠杠杆驱动",
        ),
        _chart(
            "c10",
            GROUP_RISK,
            "应收账款周转率 / 存货周转率",
            x,
            points,
            [
                _series("应收账款周转率", "line", "次", _ar_turnover),
                _series("存货周转率", "line", "次", _inventory_turnover),
            ],
            "周转次数 = 365 ÷ 周转天数（天数按平均余额计算）；指标卡仍显示周转天数",
        ),
        _chart(
            "c11",
            GROUP_RISK,
            "资产结构",
            x,
            points,
            [
                _series("商誉", "bar", "%", _asset_share("goodwill")),
                _series("应收账款", "bar", "%", _asset_share("accounts_receivable")),
                _series("存货", "bar", "%", _asset_share("inventory")),
                _series("有息负债", "bar", "%", _interest_debt_share),
            ],
            "各科目 ÷ 资产总计 × 100；有息负债 = 短期借款 + 长期借款 + 应付债券",
        ),
    ]


# ---------------------------------------------------------------------------
# 横轴：多期按年份；单期用上期比较列补一个点
# ---------------------------------------------------------------------------


def _axis(filings: list[FilingData]) -> tuple[list[str], list[Point]]:
    if len(filings) > 1:
        return [filing.period for filing in filings], [(filing, "current") for filing in filings]

    filing = filings[0]
    if not _has_previous(filing):
        return [filing.period], [(filing, "current")]
    return (
        [_previous_label(filing.period), filing.period],
        [(filing, "previous"), (filing, "current")],
    )


def _has_previous(filing: FilingData) -> bool:
    for statement in filing.values.values():
        for cells in statement.values():
            if cells.get("previous") is not None:
                return True
    return False


def _previous_label(period: str) -> str:
    if period.isdigit():
        return f"{int(period) - 1}（比较列）"
    return "上期（比较列）"


# ---------------------------------------------------------------------------
# 取值与计算
# ---------------------------------------------------------------------------


def _raw(filing: FilingData, statement: str, code: str, column: str = "current") -> float | None:
    value = filing.values.get(statement, {}).get(code, {}).get(column)
    return None if value is None else float(value)


def _metric(filing: FilingData, code: str) -> float | None:
    item = filing.metrics_by_code.get(code)
    return None if item is None or item.value is None else float(item.value)


def _average(filing: FilingData, statement: str, code: str) -> float | None:
    current = _raw(filing, statement, code, "current")
    previous = _raw(filing, statement, code, "previous")
    if current is None or previous is None:
        return None
    return (current + previous) / 2


def _growth(filing: FilingData, statement: str, code: str) -> float | None:
    current = _raw(filing, statement, code, "current")
    previous = _raw(filing, statement, code, "previous")
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


def _gross_margin(filing: FilingData, column: str) -> float | None:
    revenue = _raw(filing, "income", "revenue_total", column)
    cost = _raw(filing, "income", "cost_of_sales", column)
    if revenue is None or cost is None or revenue == 0:
        return None
    return (revenue - cost) / revenue * 100


def _net_margin(filing: FilingData, column: str) -> float | None:
    revenue = _raw(filing, "income", "revenue_total", column)
    profit = _raw(filing, "income", "net_profit", column)
    if revenue is None or profit is None or revenue == 0:
        return None
    return profit / revenue * 100


def _expense_ratio(filing: FilingData, column: str) -> float | None:
    revenue = _raw(filing, "income", "revenue_total", column)
    parts = [
        _raw(filing, "income", code, column)
        for code in ("selling_expenses", "admin_expenses", "finance_expenses")
    ]
    known = [part for part in parts if part is not None]
    if revenue is None or revenue == 0 or not known:
        return None
    return sum(known) / revenue * 100


def _roe(filing: FilingData, column: str) -> float | None:
    if column != "current":
        return None
    return _metric(filing, "roe")


def _dupont_turnover(filing: FilingData, column: str) -> float | None:
    if column != "current":
        return None
    revenue = _raw(filing, "income", "revenue_total")
    assets = _average(filing, "balance", "total_assets")
    if revenue is None or assets in (None, 0):
        return None
    return revenue / assets


def _dupont_leverage(filing: FilingData, column: str) -> float | None:
    if column != "current":
        return None
    assets = _average(filing, "balance", "total_assets")
    equity = _average(filing, "balance", "total_equity")
    if assets is None or equity in (None, 0):
        return None
    return assets / equity


def _dupont_check(filing: FilingData) -> str | None:
    net_margin = _net_margin(filing, "current")
    turnover = _dupont_turnover(filing, "current")
    leverage = _dupont_leverage(filing, "current")
    roe = _metric(filing, "roe")
    if None in (net_margin, turnover, leverage, roe):
        return None
    calculated = net_margin * turnover * leverage
    diff = calculated - roe
    if abs(diff) <= 0.5:
        return None
    return f"三因子乘积 {calculated:.1f}% 与披露 ROE {roe:.1f}% 偏差 {diff:+.1f}pct（口径差异）"


def _free_cash_flow(filing: FilingData, column: str) -> float | None:
    operational = _raw(filing, "cashflow", "ocf_net", column)
    capex = _raw(filing, "cashflow", "capex_paid", column)
    if operational is None or capex is None:
        return None
    return operational - capex


def _capex_missing(filings: list[FilingData]) -> list[str]:
    if all(_raw(filing, "cashflow", "capex_paid") is None for filing in filings):
        return ["购建长期资产支付的现金"]
    return []


def _cash_content(filing: FilingData, column: str) -> float | None:
    operational = _raw(filing, "cashflow", "ocf_net", column)
    profit = _raw(filing, "income", "net_profit", column)
    if operational is None or profit is None or profit == 0:
        return None
    return operational / profit


def _debt_ratio(filing: FilingData, column: str) -> float | None:
    liabilities = _raw(filing, "balance", "total_liabilities", column)
    assets = _raw(filing, "balance", "total_assets", column)
    if liabilities is None or assets is None or assets == 0:
        return None
    return liabilities / assets * 100


def _turnover_times(filing: FilingData, metric_code: str, column: str) -> float | None:
    if column != "current":
        return None
    days = _metric(filing, metric_code)
    if days is None or days <= 0:
        return None
    return 365 / days


def _ar_turnover(filing: FilingData, column: str) -> float | None:
    return _turnover_times(filing, "ar_turnover_days", column)


def _inventory_turnover(filing: FilingData, column: str) -> float | None:
    return _turnover_times(filing, "inventory_turnover_days", column)


def _interest_debt(filing: FilingData, column: str) -> float | None:
    parts = [
        _raw(filing, "balance", code, column)
        for code in ("short_term_borrowings", "long_term_borrowings", "bonds_payable")
    ]
    known = [part for part in parts if part is not None]
    if not known:
        return None
    return sum(known)


def _asset_share(code: str) -> Accessor:
    def accessor(filing: FilingData, column: str) -> float | None:
        value = _raw(filing, "balance", code, column)
        assets = _raw(filing, "balance", "total_assets", column)
        if value is None or assets is None or assets == 0:
            return None
        return value / assets * 100

    return accessor


def _interest_debt_share(filing: FilingData, column: str) -> float | None:
    debt = _interest_debt(filing, column)
    assets = _raw(filing, "balance", "total_assets", column)
    if debt is None or assets is None or assets == 0:
        return None
    return debt / assets * 100


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _series(
    name: str,
    kind: str,
    unit: str,
    accessor: Accessor,
    yaxis: int = 0,
    sign_colors: bool = False,
    mark_line: float | None = None,
    mark_label: str = "",
) -> dict[str, object]:
    return {
        "name": name,
        "type": kind,
        "unit": unit,
        "yAxisIndex": yaxis,
        "accessor": accessor,
        "sign_colors": sign_colors,
        "markLine": None if mark_line is None else {"value": mark_line, "label": mark_label},
    }


def _chart(
    chart_id: str,
    group: str,
    title: str,
    x: list[str],
    points: list[Point],
    specs: list[dict[str, object]],
    caliber: str,
    note: str | None = None,
    extra_missing: list[str] | None = None,
) -> dict[str, object]:
    series: list[dict[str, object]] = []
    for spec in specs:
        accessor = spec.pop("accessor")
        spec["data"] = [_round(accessor(filing, column)) for filing, column in points]
        series.append(spec)

    missing = [item["name"] for item in series if all(value is None for value in item["data"])]
    if extra_missing:
        missing.extend(extra_missing)

    meta: dict[str, object] = {"caliber": caliber, "sources": [], "missing": missing}
    if note:
        meta["note"] = note
    return {
        "id": chart_id,
        "group": group,
        "title": title,
        "x": x,
        "series": series,
        "meta": meta,
    }


def group_charts(charts: list[dict[str, object]]) -> list[dict[str, object]]:
    """按固定顺序分组，供模板渲染分组标题。"""
    return [
        {"title": group, "charts": [chart for chart in charts if chart["group"] == group]}
        for group in (GROUP_PROFIT, GROUP_CASH, GROUP_RISK)
    ]
