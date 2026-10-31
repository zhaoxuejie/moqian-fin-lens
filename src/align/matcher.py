from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Iterable, Sequence

from schema import Schema, load_accounts

PREFIXES = ("其中：", "其中:", "减：", "减:", "加：", "加:")
UNIT_SUFFIXES = ("（人民币元）", "(人民币元)", "（元）", "(元)", "（万元）", "(万元)")


@dataclass(frozen=True)
class Match:
    raw_label: str
    page: int
    statement: str
    account_code: str | None
    confidence: float
    source: str  # rule | fuzzy | unaligned
    reason: str | None = None

    @property
    def needs_review(self) -> bool:
        return self.source == "fuzzy"

    @property
    def aligned(self) -> bool:
        return self.account_code is not None


def normalize_label(text: str) -> str:
    value = text.strip()
    for suffix in UNIT_SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break
    for prefix in PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value.rstrip("：:")


def match_label(
    label: str,
    page: int,
    statement: str,
    schema: Schema,
    threshold: float = 0.85,
) -> Match:
    """把单个原文科目名映射到标准科目；映射不了就明确返回 unaligned。"""
    normalized = normalize_label(label)
    is_section_header = label.strip().endswith(("：", ":"))

    account = schema.resolve(normalized) or schema.resolve(label.strip())
    if account is not None and account.statement == statement:
        return Match(label, page, statement, account.code, 1.0, "rule")

    best_ratio = 0.0
    best_code: str | None = None
    if is_section_header:
        return Match(label, page, statement, None, 0.0, "unaligned", reason="section_header")
    if len(normalized) >= 4:
        for candidate in schema.accounts_for_statement(statement):
            for alias in candidate.aliases:
                ratio = difflib.SequenceMatcher(None, normalized, alias).ratio()
                if ratio > best_ratio:
                    best_ratio, best_code = ratio, candidate.code

    if best_code is not None and best_ratio >= threshold:
        return Match(
            label,
            page,
            statement,
            best_code,
            round(best_ratio, 3),
            "fuzzy",
            reason="low_confidence" if best_ratio < 0.95 else None,
        )

    reason = "statement_mismatch" if account is not None else "no_match"
    return Match(label, page, statement, None, 0.0, "unaligned", reason=reason)


def align_entries(
    entries: Iterable[tuple[int, str, str]],
    schema: Schema | None = None,
    threshold: float = 0.85,
) -> list[Match]:
    """entries 为 (页码, 报表类型, 原文科目名) 序列；返回逐条匹配结果。"""
    schema = schema or load_accounts()
    return [
        match_label(label, page, statement, schema, threshold)
        for page, statement, label in entries
    ]


def split_unaligned(matches: Sequence[Match]) -> tuple[list[Match], list[Match]]:
    aligned = [item for item in matches if item.aligned]
    unaligned = [item for item in matches if not item.aligned]
    return aligned, unaligned
