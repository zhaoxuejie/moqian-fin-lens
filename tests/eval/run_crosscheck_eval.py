"""交叉核对评估（TASK-024）：不看金标，拿年报自己的另一处披露核对产品输出。

- 断言 A：报表取到的营业收入（本期、上期）与「主要会计数据」一节的营业收入一致。
- 断言 B：指标标为「原文未披露：X」时，三张报表的页范围里确实没有科目 X 的金额行。

金标也是脚本生成的，两边出同一种错时（比如都没读表头单位）金标评测照样通过。
所以这里的行读取、金额换算都自己写，不复用产品的表格还原、单位识别和科目匹配。

用法：
    .venv/bin/python tests/eval/run_crosscheck_eval.py > tests/eval/reports/crosscheck.txt
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import PdfDoc, locate_statements  # noqa: E402
from schema import Schema, load_accounts  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
PDF_DIR = EVAL_DIR / "pdf"

UNIT_FACTORS = {"元": Decimal(1), "千元": Decimal(1000), "万元": Decimal(10000), "百万元": Decimal(10**6), "亿元": Decimal(10**8)}
UNIT_NOTE = re.compile(r"^[（(](元|千元|万元|百万元|亿元)[)）]$")
PAGE_UNIT = re.compile(r"单位\s*[:：]\s*(?:人民币)?\s*(百万元|千元|万元|亿元|元)")
AMOUNT = re.compile(r"^\(?-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2}|\d+)\)?$")
EMPTY = {"-", "—", "－", "--", "——"}
RESTATED = re.compile(r"追溯调整或重述以前年度会计数据\s*[√☑]\s*是")
REVENUE_LABEL = re.compile(r"^(营业总收入|营业收入)(?:[（(](元|千元|万元|百万元|亿元)[)）])?$")
# 报表行首的编号与连接词：「一、」「1.」「其中：」「加：」「减：」
LABEL_PREFIX = re.compile(r"^(?:[一二三四五六七八九十]+、|\d+\s*[\.．、]|其中[:：]|加[:：]|减[:：])+")
# 附注列：「七、29」「五(1)」「附注七、3」
NOTE_TOKEN = re.compile(r"^(?:附注)?[一二三四五六七八九十]+[、.]?\(?\d+\)?$")
SECTION_SPAN = 3
REVENUE_CODES = {"营业收入": "revenue", "营业总收入": "revenue_total"}


def to_yuan(raw: str, unit: str) -> Decimal:
    """原文金额 → 元。括号与负号都表示负数。"""
    text = raw.replace(",", "")
    negative = text.startswith("(") or text.startswith("-")
    value = Decimal(text.strip("()-")) * UNIT_FACTORS[unit]
    return -value if negative else value


def statement_ranges(pages: list[str]) -> dict[str, tuple[int, int]]:
    """三表页范围，与产品 build_filing 同一算法（定位本身另有 30/30 的评测）。"""
    located = locate_statements(pages)
    starts = {"income": located.income.start, "balance": located.balance.start, "cashflow": located.cashflow.start}
    ordered = sorted(starts.values())
    ranges = {}
    for kind, start in starts.items():
        position = ordered.index(start)
        end = ordered[position + 1] - 1 if position + 1 < len(ordered) else min(start + 2, len(pages))
        ranges[kind] = (start, end)
    return ranges


# ---------- 断言 A ----------


@dataclass(frozen=True)
class MainRevenue:
    label: str  # 营业收入 / 营业总收入
    current: Decimal
    previous: Decimal
    raw: tuple[str, str]
    unit: str
    page: int
    restated: bool


def read_main_revenue(pages: list[str], before: int) -> tuple[MainRevenue | None, str | None]:
    """在第 before 页之前找「主要会计数据」一节的营业收入行；找不到时返回原因。"""
    start = next((i for i, text in enumerate(pages[: before - 1], start=1) if "主要会计数据" in text), None)
    if start is None:
        return None, "三表之前没有「主要会计数据」一节"
    section = pages[start - 1][pages[start - 1].index("主要会计数据"):]
    restated = bool(RESTATED.search(re.sub(r"\s+", "", section)))
    for number in range(start, min(start + SECTION_SPAN, before - 1) + 1):
        text = section if number == start else pages[number - 1]
        found = _revenue_line(text, restated)
        if found is None:
            continue
        label, amounts, label_unit = found
        unit = label_unit or _page_unit(pages[number - 1]) or "元"
        return (
            MainRevenue(label, to_yuan(amounts[0], unit), to_yuan(amounts[1], unit), amounts, unit, number, restated),
            None,
        )
    return None, f"P.{start} 起 {SECTION_SPAN + 1} 页内没有带金额的营业收入行"


def _page_unit(text: str) -> str | None:
    match = PAGE_UNIT.search(text)
    return match.group(1) if match else None


def _revenue_line(text: str, restated: bool) -> tuple[str, tuple[str, str], str | None] | None:
    """营业收入行：科目名（可带单位说明）后面紧跟金额；追溯调整时上期取「调整后」。"""
    after_first = _adjusted_after_first(text) if restated else None
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        match = REVENUE_LABEL.match(tokens[0])
        if not match:
            continue
        label_unit = match.group(2)
        rest = tokens[1:]
        if rest and UNIT_NOTE.match(rest[0]):
            label_unit = UNIT_NOTE.match(rest.pop(0)).group(1)
        needed = 3 if restated else 2
        if len(rest) < needed or not all(AMOUNT.match(token) for token in rest[:needed]):
            continue  # 叙述性提及，或这一行不是表格行
        if restated:
            previous = rest[2] if after_first is False else rest[1]
        else:
            previous = rest[1]
        return match.group(1), (rest[0], previous), label_unit
    return None


def _adjusted_after_first(text: str) -> bool | None:
    """表头里「调整前」在「调整后」之前时返回 False（上期取第 3 个金额）。"""
    before, after = text.find("调整前"), text.find("调整后")
    if before < 0 or after < 0:
        return None
    return after < before


@dataclass(frozen=True)
class RevenueCheck:
    status: str  # 一致 / 不一致 / 未核对
    detail: str
    main: MainRevenue | None = None


def check_revenue(values: dict, pages: list[str], ranges: dict[str, tuple[int, int]]) -> RevenueCheck:
    main, reason = read_main_revenue(pages, min(start for start, _ in ranges.values()))
    if main is None:
        return RevenueCheck("未核对", reason or "")
    product = values.get("income", {}).get(REVENUE_CODES[main.label], {})
    current, previous = product.get("current"), product.get("previous")
    ok = current == main.current and previous == main.previous
    restated = "，上期按调整后" if main.restated else ""
    detail = (
        f"主要会计数据 P.{main.page} {main.label} {main.raw[0]} / {main.raw[1]}（{main.unit}{restated}）"
        f" = {main.current} / {main.previous} 元；报表 {current} / {previous} 元"
    )
    return RevenueCheck("一致" if ok else "不一致", detail, main)


# ---------- 断言 B ----------


@dataclass(frozen=True)
class MissingCheck:
    metric: str
    account: str
    status: str  # 通过 / 列示为空 / 违反
    evidence: tuple[str, ...] = ()


def account_lines(account_names: set[str], pages: list[str], ranges: dict[str, tuple[int, int]]):
    """逐行找科目名，产出 (页码, 后面是金额还是空, 原文行)。一行里可能挤着几个科目。"""
    numbers = sorted({n for start, end in ranges.values() for n in range(start, end + 1)})
    for number in numbers:
        for line in pages[number - 1].splitlines():
            tokens = line.split()
            for index, token in enumerate(tokens):
                name = re.sub(r"[（(].*$", "", LABEL_PREFIX.sub("", token))
                if name not in account_names:
                    continue
                following = [t for t in tokens[index + 1:index + 3] if not NOTE_TOKEN.match(t)]
                if following and AMOUNT.match(following[0]):
                    yield number, "amount", line.strip()
                elif following and following[0] in EMPTY:
                    yield number, "empty", line.strip()


def check_missing(metrics, pages: list[str], ranges: dict[str, tuple[int, int]], schema: Schema | None = None):
    """凡标「原文未披露」的指标，逐个依赖科目到原文里确认。"""
    schema = schema or load_accounts()
    results: list[MissingCheck] = []
    for metric in metrics:
        reason = metric.missing_reason or ""
        if metric.value is not None or not reason.startswith("原文未披露："):
            continue
        for code in reason.split("：", 1)[1].split("、"):
            account = schema.by_code[code]
            names = {account.label, *account.aliases}
            hits = list(account_lines(names, pages, ranges))
            amounts = tuple(f"P.{page} {line[:80]}" for page, kind, line in hits if kind == "amount")
            empties = tuple(f"P.{page} {line[:80]}" for page, kind, line in hits if kind == "empty")
            if amounts:
                results.append(MissingCheck(metric.code, code, "违反", amounts))
            elif empties:
                results.append(MissingCheck(metric.code, code, "列示为空", empties))
            else:
                results.append(MissingCheck(metric.code, code, "通过"))
    return results


# ---------- 汇总 ----------


def read_pages(pdf: Path) -> list[str]:
    with PdfDoc(str(pdf)) as doc:
        return [doc.page_text(number) for number in range(1, doc.page_count + 1)]


def period_of(pdf: Path) -> str:
    return re.search(r"(\d{4})年", pdf.stem).group(1)


def main() -> int:
    from dashboard.session import build_filing

    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    if not pdfs:
        print("缺少评估集 PDF")
        return 1
    revenue_ok = revenue_total = 0
    violations = empties = passed = 0
    for pdf in pdfs:
        filing = build_filing(pdf, period_of(pdf))
        pages = read_pages(pdf)
        ranges = statement_ranges(pages)
        print(f"== {pdf.stem}")
        revenue = check_revenue(filing.values, pages, ranges)
        print(f"  [A] {revenue.status} {revenue.detail}")
        revenue_total += 2
        if revenue.status == "一致":
            revenue_ok += 2
        for item in check_missing(filing.metrics, pages, ranges):
            print(f"  [B] {item.status} {item.metric} 缺 {item.account}")
            for evidence in item.evidence:
                print(f"        {evidence}")
            violations += item.status == "违反"
            empties += item.status == "列示为空"
            passed += item.status == "通过"
    print()
    print(f"断言 A：营业收入本期、上期一致 {revenue_ok}/{revenue_total}")
    print(f"断言 B：原文未披露 {violations + empties + passed} 处，通过 {passed}、列示为空 {empties}、违反 {violations}")
    return 0 if revenue_ok == revenue_total and violations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
