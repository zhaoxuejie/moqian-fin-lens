from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDef:
    code: str
    label: str
    unit: str  # 元 | % | 倍 | 天
    requires: tuple[str, ...]
    formula: str
    # 依赖科目未列示时的替代科目，如 (("revenue_total", "revenue"),)：利润表不列营业总收入时用营业收入
    fallbacks: tuple[tuple[str, str], ...] = ()
    # True：依赖科目至少列示一项即可计算，未列示的项不计入（如有息负债）
    any_of: bool = False


# 营业总收入只在含金融类收入的报表里单列；没有这一行的公司，营业总收入等于营业收入
TOP_LINE = (("revenue_total", "revenue"),)
TOP_LINE_NOTE = "（未列示营业总收入时用营业收入）"

METRICS: tuple[MetricDef, ...] = (
    MetricDef("revenue_total", "营业总收入", "元", ("revenue_total",), "取合并利润表「营业总收入」"),
    MetricDef("revenue", "营业收入", "元", ("revenue",), "取合并利润表「营业收入」"),
    MetricDef(
        "net_profit_attributable",
        "归属于母公司股东的净利润",
        "元",
        ("net_profit_attributable",),
        "取合并利润表「归属于母公司股东的净利润」",
    ),
    MetricDef(
        "net_profit_deducted",
        "扣非净利润",
        "元",
        ("net_profit_deducted",),
        "取合并利润表「扣除非经常性损益后的净利润」",
    ),
    MetricDef(
        "gross_margin",
        "毛利率",
        "%",
        ("revenue_total", "cost_of_sales"),
        "（营业总收入 - 营业成本）÷ 营业总收入 × 100" + TOP_LINE_NOTE,
        fallbacks=TOP_LINE,
    ),
    MetricDef(
        "net_margin",
        "净利率",
        "%",
        ("net_profit", "revenue_total"),
        "净利润 ÷ 营业总收入 × 100" + TOP_LINE_NOTE,
        fallbacks=TOP_LINE,
    ),
    MetricDef(
        "roe",
        "净资产收益率（ROE）",
        "%",
        ("net_profit_attributable", "equity_attributable_holders"),
        "归母净利润 ÷ 平均归属于母公司所有者权益 × 100",
    ),
    MetricDef("roa", "总资产收益率", "%", ("net_profit", "total_assets"), "净利润 ÷ 平均总资产 × 100"),
    MetricDef("operating_cash_flow", "经营活动现金流净额", "元", ("ocf_net",), "取合并现金流量表「经营活动产生的现金流量净额」"),
    MetricDef("cash_content", "现金含量", "倍", ("ocf_net", "net_profit"), "经营现金流 ÷ 净利润"),
    MetricDef("accounts_receivable", "应收账款", "元", ("accounts_receivable",), "取合并资产负债表「应收账款」"),
    MetricDef(
        "ar_turnover_days",
        "应收账款周转天数",
        "天",
        ("accounts_receivable", "revenue_total"),
        "365 ÷（营业总收入 ÷ 平均应收账款）" + TOP_LINE_NOTE,
        fallbacks=TOP_LINE,
    ),
    MetricDef("inventory", "存货", "元", ("inventory",), "取合并资产负债表「存货」"),
    MetricDef(
        "inventory_turnover_days",
        "存货周转天数",
        "天",
        ("inventory", "cost_of_sales"),
        "365 ÷（营业成本 ÷ 平均存货）",
    ),
    MetricDef("goodwill", "商誉", "元", ("goodwill",), "取合并资产负债表「商誉」"),
    MetricDef(
        "interest_bearing_debt",
        "有息负债",
        "元",
        ("short_term_borrowings", "long_term_borrowings", "bonds_payable"),
        "短期借款 + 长期借款 + 应付债券（至少列示一项，未列示的项不计入）",
        any_of=True,
    ),
    MetricDef("debt_ratio", "资产负债率", "%", ("total_liabilities", "total_assets"), "负债合计 ÷ 资产总计 × 100"),
    MetricDef(
        "expense_ratio",
        "三费占收入比",
        "%",
        ("selling_expenses", "admin_expenses", "finance_expenses", "revenue_total"),
        "（销售费用 + 管理费用 + 财务费用）÷ 营业总收入 × 100" + TOP_LINE_NOTE,
        fallbacks=TOP_LINE,
    ),
    MetricDef(
        "revenue_growth",
        "营收增速",
        "%",
        ("revenue_total",),
        "（本期营业总收入 - 上期）÷ |上期| × 100" + TOP_LINE_NOTE,
        fallbacks=TOP_LINE,
    ),
    MetricDef(
        "net_profit_growth",
        "扣非增速",
        "%",
        ("net_profit_deducted",),
        "（本期扣非净利润 - 上期）÷ |上期| × 100",
    ),
)

METRIC_BY_CODE = {metric.code: metric for metric in METRICS}
