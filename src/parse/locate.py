from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from core.errors import AppError, ErrorCode

STATEMENT_KINDS = ("income", "balance", "cashflow")

HEADING_ALIASES: dict[str, tuple[str, ...]] = {
    "income": ("合并利润表", "合并利润及利润分配表"),
    "balance": ("合并资产负债表",),
    "cashflow": ("合并现金流量表",),
}

# 主表页一定出现的科目之一，用来排除目录页与附注里的同名段落
REQUIRED_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "income": ("营业总收入", "营业收入", "营业成本", "利润总额", "净利润"),
    "balance": ("流动资产", "资产总计", "负债合计", "所有者权益"),
    "cashflow": (
        "经营活动产生的现金流量",
        "投资活动产生的现金流量",
        "筹资活动产生的现金流量",
    ),
}

# 报表页头部特征：区别于「编制合并资产负债表时……」这类叙述性提及
STATEMENT_HEADER_MARKERS = (
    "单位：元",
    "单位:元",
    "单位：人民币元",
    "单位：千元",
    "单位：万元",
    "编制单位",
)

# 管理层讨论里的分析表也叫「利润表及现金流量表相关科目变动分析表」，必须排除
EXCLUDE_PHRASES = ("变动分析表", "科目变动", "主要会计数据", "主要财务指标")

_PARENT_PREFIX = "母公司"


@dataclass(frozen=True)
class StatementRange:
    start: int
    end: int


@dataclass(frozen=True)
class LocatedStatements:
    income: StatementRange
    balance: StatementRange
    cashflow: StatementRange

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {
            "income": {"start": self.income.start, "end": self.income.end},
            "balance": {"start": self.balance.start, "end": self.balance.end},
            "cashflow": {"start": self.cashflow.start, "end": self.cashflow.end},
        }


def compress_whitespace(text: str) -> str:
    """去掉所有空白（含全角空格），便于跨行标题匹配；与数值归一 normalize 区分。"""
    return re.sub(r"\s+", "", text)


def find_heading(normalized: str, kind: str) -> int | None:
    """返回首个非「母公司」标题的出现位置；找不到返回 None。"""
    for alias in HEADING_ALIASES[kind]:
        index = normalized.find(alias)
        while index != -1:
            prefix = normalized[max(0, index - len(_PARENT_PREFIX)):index]
            if not prefix.endswith(_PARENT_PREFIX):
                return index
            index = normalized.find(alias, index + 1)
    return None


def looks_like_toc(normalized: str) -> bool:
    return "目录" in normalized[:120]


def is_statement_page(text: str, kind: str, next_text: str | None = None) -> bool:
    normalized = compress_whitespace(text)
    if len(normalized) < 50:
        return False
    if looks_like_toc(normalized):
        return False
    if any(phrase in normalized for phrase in EXCLUDE_PHRASES):
        return False
    if find_heading(normalized, kind) is None:
        return False
    if not any(marker in normalized for marker in STATEMENT_HEADER_MARKERS):
        # 兜底：报表页数字密度显著高于叙述页
        if sum(char.isdigit() for char in normalized) < 80:
            return False
    if any(account in normalized for account in REQUIRED_ACCOUNTS[kind]):
        return True
    # 表格可能刚好在标题页断开：科目行落在下一页
    if next_text is not None:
        following = compress_whitespace(next_text)
        if any(account in following for account in REQUIRED_ACCOUNTS[kind]):
            return True
    return False


def detect_start_pages(pages: Sequence[str]) -> dict[str, int | None]:
    """返回三表的起始页码（1 基），找不到的为 None。"""
    starts: dict[str, int | None] = {}
    for kind in STATEMENT_KINDS:
        starts[kind] = None
        for index, text in enumerate(pages):
            following = pages[index + 1] if index + 1 < len(pages) else None
            if is_statement_page(text, kind, following):
                starts[kind] = index + 1
                break
    return starts


def _cashflow_end(pages: Sequence[str], start: int) -> int:
    """现金流量表通常 2～3 页，之后是所有者权益变动表或母公司报表。"""
    limit = min(start + 6, len(pages))
    for page_number in range(start + 1, limit + 1):
        normalized = compress_whitespace(pages[page_number - 1])
        if "所有者权益变动表" in normalized or "母公司资产负债表" in normalized:
            return page_number - 1
    return min(start + 3, len(pages))


def build_ranges(
    starts: dict[str, int | None],
    page_count: int,
    pages: Sequence[str] | None = None,
) -> LocatedStatements:
    missing = [kind for kind in STATEMENT_KINDS if starts.get(kind) is None]
    if missing:
        raise AppError(
            ErrorCode.STATEMENT_LOCATE_FAILED,
            "三表定位失败",
            {"missing": missing, "found": {k: v for k, v in starts.items() if v}},
        )

    ordered = sorted((starts[kind], kind) for kind in STATEMENT_KINDS if starts[kind] is not None)
    ranges: dict[str, StatementRange] = {}
    for position, (start, kind) in enumerate(ordered):
        if position + 1 < len(ordered):
            end = ordered[position + 1][0] - 1
        elif pages is not None:
            end = _cashflow_end(pages, start)
        else:
            end = min(start + 5, page_count)
        ranges[kind] = StatementRange(start=start, end=max(start, end))

    return LocatedStatements(
        income=ranges["income"],
        balance=ranges["balance"],
        cashflow=ranges["cashflow"],
    )


def locate_statements(pages: Sequence[str]) -> LocatedStatements:
    page_count = len(pages)
    if page_count == 0:
        raise AppError(ErrorCode.STATEMENT_LOCATE_FAILED, "PDF 没有可解析页面", {"pages": 0})
    return build_ranges(detect_start_pages(pages), page_count, pages)
