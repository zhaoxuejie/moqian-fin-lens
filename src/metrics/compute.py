from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

import re

from align import normalize_label
from metrics.registry import METRICS, MetricDef
from parse.table import StatementRow
from schema import Schema, load_accounts

ZERO = Decimal(0)
NUMBERING = re.compile(r"^[一二三四五六七八九十]+、")


@dataclass(frozen=True)
class MetricResult:
    code: str
    label: str
    value: Decimal | None
    unit: str
    formula: str
    missing_reason: str | None = None
    yoy: Decimal | None = None
    yoy_unit: str | None = None
    yoy_note: str | None = None


@dataclass(frozen=True)
class CheckResult:
    rule: str
    status: str  # passed | failed | skipped
    diff: Decimal | None = None
    detail: str = ""


def _suffix_account(label: str, schema: Schema):
    """合并单元格会把多个科目名挤在一起，退化为「最长后缀」匹配。

    仅当剩余前缀本身不是另一个科目、且不是「流动 / 非流动 / 归属于」这类限定词时才接受，
    避免把「流动负债合计」误挂到「负债合计」。
    """
    if label.startswith(("流动", "非流动", "归属于")):
        return None
    for alias in sorted(schema.alias_index, key=len, reverse=True):
        if len(alias) < 2 or not label.endswith(alias) or len(label) <= len(alias):
            continue
        prefix = label[: -len(alias)]
        if schema.resolve(prefix) is not None:
            continue
        if len(label) > len(alias) + 8:
            continue
        return schema.by_code.get(schema.alias_index[alias])
    return None


def _prefix_account(label: str, schema: Schema):
    """跨行折行会把科目名截断，行上的数字本身是完整的。

    例如「购建固定资产、无形资产和其他长」是标准科目名的前缀。仅当标签是
    某个标准别名的前缀、长度 ≥ 别名的 60%，且只指向唯一科目时才采用，
    避免把「营业利润」这类短名误挂到更长的近似科目上。
    """
    if len(label) < 6:
        return None
    codes = {
        schema.alias_index[alias]
        for alias in schema.alias_index
        if len(alias) > len(label) and len(label) >= len(alias) * 0.6 and alias.startswith(label)
    }
    if len(codes) != 1:
        return None
    return schema.by_code.get(next(iter(codes)))


def _resolved_rows(rows_by_kind: Mapping[str, list[StatementRow]], schema: Schema):
    """逐行产出 (标准科目, 行, 是否精确命中, 各期数值)；取数与页码索引共用同一套命中规则。"""
    for origin, rows in rows_by_kind.items():
        for row in rows:
            label = re.sub(r"\s+", "", NUMBERING.sub("", normalize_label(row.label)))
            account = schema.resolve(label)
            exact = account is not None
            if account is None:
                account = _suffix_account(label, schema)
            if account is None:
                account = _prefix_account(label, schema)
            if account is None:
                continue
            # 跨表行（利润表页里的母公司资产负债表尾行）一律忽略，避免口径串表
            if account.statement != origin:
                continue
            periods = {
                cell.period: cell.value
                for cell in row.cells
                if cell.value is not None
            }
            if not periods:
                continue
            yield account, row, exact, periods


def values_from_rows(
    rows_by_kind: Mapping[str, list[StatementRow]],
    schema: Schema | None = None,
) -> dict[str, dict[str, dict[str, Decimal]]]:
    """把三表行映射成 values[statement][account_code][period] = Decimal。

    分层优先：精确科目名优先于后缀匹配；同一科目多次披露时保留首个精确值，
    避免附注或母公司报表覆盖主表。
    """
    schema = schema or load_accounts()
    entries: dict[tuple[str, str], list[tuple[bool, dict[str, Decimal]]]] = {}

    for account, _row, exact, periods in _resolved_rows(rows_by_kind, schema):
        entries.setdefault((account.statement, account.code), []).append((exact, periods))

    values: dict[str, dict[str, dict[str, Decimal]]] = {}
    for (statement, code), items in entries.items():
        merged: dict[str, Decimal] = {}
        # 按行出现顺序取值：合并报表在三表页里先出现，母公司报表在后
        for _exact, periods in items:
            for period, value in periods.items():
                merged.setdefault(period, value)
        values.setdefault(statement, {})[code] = merged
    return values


def pages_from_rows(
    rows_by_kind: Mapping[str, list[StatementRow]],
    schema: Schema | None = None,
) -> dict[tuple[str, str], int]:
    """标准科目 → 取数行页码：与 values_from_rows 同序取首个出现的行，供异常项标注出处。"""
    schema = schema or load_accounts()
    pages: dict[tuple[str, str], int] = {}
    for account, row, _exact, _periods in _resolved_rows(rows_by_kind, schema):
        pages.setdefault((account.statement, account.code), row.page)
    return pages

def _pick(values, kind: str, code: str, period: str) -> Decimal | None:
    return values.get(kind, {}).get(code, {}).get(period)


def _current(values, kind: str = "income") -> dict[str, Decimal]:
    return {code: periods["current"] for code, periods in values.get(kind, {}).items() if "current" in periods}


def _average(values, kind: str, code: str) -> Decimal | None:
    current = _pick(values, kind, code, "current")
    previous = _pick(values, kind, code, "previous")
    if current is None:
        return None
    if previous is None:
        return current
    return (current + previous) / 2


def _pct(value: Decimal | None) -> Decimal | None:
    return None if value is None else (value * 100)


def _div(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _def_missing(metric: MetricDef, income: dict[str, Decimal]) -> str | None:
    missing = [code for code in metric.requires if code not in income]
    if not missing:
        return None
    return "原文未披露：" + "、".join(missing)


def top_line(values: Mapping[str, dict[str, dict[str, Decimal]]], period: str = "current") -> Decimal | None:
    """营业总收入；利润表没有单列这一行时用营业收入（两者此时相等）。"""
    income = values.get("income", {})
    if "revenue_total" in income:
        return income["revenue_total"].get(period)
    return income.get("revenue", {}).get(period)


def _growth(current: Decimal | None, previous: Decimal | None) -> tuple[Decimal | None, str | None]:
    if current is None or previous is None:
        return None, "基期数据缺失"
    if previous == 0 or previous < 0:
        return None, "不适用（基期为 0 或负）"
    return (current - previous) / abs(previous) * 100, None


def compute_metrics(
    values: Mapping[str, dict[str, dict[str, Decimal]]],
    schema: Schema | None = None,
) -> list[MetricResult]:
    """按 registry 顺序计算 20 项指标；缺数据时给出原因，不落 0。"""
    income = _current(values, "income")
    balance = _current(values, "balance")
    cashflow = _current(values, "cashflow")

    def pick(kind: str, code: str) -> Decimal | None:
        bucket = {"income": income, "balance": balance, "cashflow": cashflow}[kind]
        return bucket.get(code)

    def present(code: str) -> bool:
        return code in income or code in balance or code in cashflow

    results: list[MetricResult] = []

    for metric in METRICS:
        fallback = dict(metric.fallbacks)

        def available(code: str) -> bool:
            return present(code) or (code in fallback and present(fallback[code]))

        if metric.any_of:
            missing_codes = [] if any(available(code) for code in metric.requires) else list(metric.requires)
        else:
            missing_codes = [code for code in metric.requires if not available(code)]
        missing: str | None = (
            None if not missing_codes else "原文未披露：" + "、".join(missing_codes)
        )
        value: Decimal | None = None
        note: str | None = None

        if missing is None:
            if metric.code == "revenue_total":
                value = pick("income", "revenue_total")
            elif metric.code == "revenue":
                value = pick("income", "revenue")
            elif metric.code == "net_profit_attributable":
                value = pick("income", "net_profit_attributable")
            elif metric.code == "net_profit_deducted":
                value = pick("income", "net_profit_deducted")
            elif metric.code == "operating_cash_flow":
                value = pick("cashflow", "ocf_net")
            elif metric.code == "gross_margin":
                revenue = top_line(values)
                cost = pick("income", "cost_of_sales")
                value = _pct(_div(None if revenue is None or cost is None else revenue - cost, revenue))
            elif metric.code == "net_margin":
                value = _pct(_div(pick("income", "net_profit"), top_line(values)))
            elif metric.code == "roe":
                value = _pct(
                    _div(pick("income", "net_profit_attributable"), _average(values, "balance", "equity_attributable_holders"))
                )
            elif metric.code == "roa":
                value = _pct(_div(pick("income", "net_profit"), _average(values, "balance", "total_assets")))
            elif metric.code == "cash_content":
                numerator = pick("cashflow", "ocf_net") or pick("income", "ocf_net")
                value = _div(numerator, pick("income", "net_profit"))
            elif metric.code == "accounts_receivable":
                value = pick("balance", "accounts_receivable")
            elif metric.code == "ar_turnover_days":
                turnover = _div(top_line(values), _average(values, "balance", "accounts_receivable"))
                value = None if turnover in (None, ZERO) else Decimal(365) / turnover
            elif metric.code == "inventory":
                value = pick("balance", "inventory")
            elif metric.code == "inventory_turnover_days":
                turnover = _div(
                    pick("income", "cost_of_sales"), _average(values, "balance", "inventory")
                )
                value = None if turnover in (None, ZERO) else Decimal(365) / turnover
            elif metric.code == "goodwill":
                value = pick("balance", "goodwill")
            elif metric.code == "interest_bearing_debt":
                parts = [
                    pick("balance", "short_term_borrowings"),
                    pick("balance", "long_term_borrowings"),
                    pick("balance", "bonds_payable"),
                ]
                value = sum((part for part in parts if part is not None), ZERO)
            elif metric.code == "debt_ratio":
                value = _pct(_div(pick("balance", "total_liabilities"), pick("balance", "total_assets")))
            elif metric.code == "expense_ratio":
                expense = sum(
                    (
                        pick("income", code) or ZERO
                        for code in ("selling_expenses", "admin_expenses", "finance_expenses")
                    ),
                    ZERO,
                )
                value = _pct(_div(expense, top_line(values)))
            elif metric.code == "revenue_growth":
                value, note = _growth(top_line(values), top_line(values, "previous"))
            elif metric.code == "net_profit_growth":
                value, note = _growth(
                    pick("income", "net_profit_deducted"),
                    _pick(values, "income", "net_profit_deducted", "previous"),
                )

            if value is None and missing is None:
                missing = note or "数据不足，无法计算"

        yoy = None
        yoy_unit = None
        yoy_note = None
        if metric.any_of:
            # 合计类指标的同比按合计算，不能只看第一个依赖科目
            def total(period: str) -> Decimal | None:
                parts = [_pick(values, "balance", code, period) for code in metric.requires]
                known = [part for part in parts if part is not None]
                return sum(known, ZERO) if known else None

            yoy, yoy_note = _growth(total("current"), total("previous"))
            yoy_unit = "%"
        elif metric.unit == "元" and metric.requires:
            code = metric.requires[0]
            yoy, yoy_note = _growth(
                pick("income", code) or pick("balance", code) or pick("cashflow", code),
                _pick(values, "income", code, "previous")
                or _pick(values, "balance", code, "previous")
                or _pick(values, "cashflow", code, "previous"),
            )
            yoy_unit = "%"

        results.append(
            MetricResult(
                code=metric.code,
                label=metric.label,
                value=value,
                unit=metric.unit,
                formula=metric.formula,
                missing_reason=missing,
                yoy=yoy,
                yoy_unit=yoy_unit,
                yoy_note=yoy_note,
            )
        )

    return results

def check_statements(
    values: Mapping[str, dict[str, dict[str, Decimal]]],
) -> list[CheckResult]:
    """三表勾稽：资产=负债+权益、归母+少数=净利润、利润表净利润=现金流量表净利润。"""
    checks: list[CheckResult] = []

    assets = _pick(values, "balance", "total_assets", "current")
    liabilities = _pick(values, "balance", "total_liabilities", "current")
    equity = _pick(values, "balance", "total_equity", "current")
    if assets is None or liabilities is None or equity is None:
        checks.append(CheckResult("balance_identity", "skipped", None, "资产/负债/权益科目缺失"))
    else:
        diff = assets - liabilities - equity
        checks.append(
            CheckResult(
                "balance_identity",
                "passed" if abs(diff) <= Decimal("0.01") else "failed",
                diff,
                "资产总计 - 负债合计 - 所有者权益合计",
            )
        )

    net_profit = _pick(values, "income", "net_profit", "current")
    attributable = _pick(values, "income", "net_profit_attributable", "current")
    minority = _pick(values, "income", "minority_interest", "current")
    if net_profit is None or attributable is None:
        checks.append(CheckResult("equity_split", "skipped", None, "净利润或归母净利润缺失"))
    else:
        diff = net_profit - attributable - (minority or ZERO)
        checks.append(
            CheckResult(
                "equity_split",
                "passed" if abs(diff) <= Decimal("0.01") else "failed",
                diff,
                "净利润 - 归母净利润 - 少数股东损益",
            )
        )

    cash_net_profit = _pick(values, "cashflow", "net_profit", "current")
    if net_profit is None or cash_net_profit is None:
        checks.append(
            CheckResult("net_profit_cashflow", "skipped", None, "现金流量表补充资料净利润未在页范围内")
        )
    else:
        diff = net_profit - cash_net_profit
        checks.append(
            CheckResult(
                "net_profit_cashflow",
                "passed" if abs(diff) <= Decimal("0.01") else "failed",
                diff,
                "利润表净利润 - 现金流量表净利润",
            )
        )

    return checks
