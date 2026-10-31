from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.errors import AppError, ErrorCode

UNIT_MULTIPLIERS: dict[str, Decimal] = {
    "元": Decimal(1),
    "千元": Decimal(1_000),
    "万元": Decimal(10_000),
    "百万元": Decimal(1_000_000),
    "亿元": Decimal(100_000_000),
}

# 原文用这些符号表示「未披露」，必须与 0 区分（PRD P3）
MISSING_TOKENS = {
    "",
    "-",
    "--",
    "—",
    "——",
    "–",
    "－",
    "不适用",
    "无",
    "n/a",
    "na",
    "null",
    "none",
    "/",
}

_FULLWIDTH: dict[int, str] = {ord("０") + offset: str(offset) for offset in range(10)}
_FULLWIDTH.update(
    {
        ord("．"): ".",
        ord("，"): ",",
        ord("（"): "(",
        ord("）"): ")",
        ord("－"): "-",
        ord("％"): "%",
        ord("＋"): "+",
        ord("　"): " ",
    }
)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class NormalizedNumber:
    value: Decimal | None
    unit: str
    is_missing: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
            "is_missing": self.is_missing,
        }


def _missing(unit: str) -> NormalizedNumber:
    return NormalizedNumber(value=None, unit=unit, is_missing=True)


def normalize(value_text: str | None, unit_hint: str | None = None) -> NormalizedNumber:
    """把财报单元格的原文字符串归一为标准「元」或百分比。

    规则：
    - 千分位、全角数字、全角括号、货币符号一律先清洗；
    - ``(1,234.00)`` 表示负数；``—`` ``-`` 空串视作「未披露」，**不视为 0**；
    - 单位可来自 ``unit_hint``，也可写在数字后面（``1.2亿元``），后者优先；
    - 百分比返回百分数本身（12.34% -> 12.34，unit="%"），不做倍数换算。
    """
    unit = unit_hint or "元"
    if unit not in UNIT_MULTIPLIERS:
        raise AppError(
            ErrorCode.INVALID_PARAMS,
            "未知的金额单位",
            {"unit_hint": unit, "allowed": sorted(UNIT_MULTIPLIERS)},
        )

    if value_text is None:
        return _missing(unit)

    raw = str(value_text)
    text = raw.translate(_FULLWIDTH).replace("\u00a0", " ").strip()
    if text.lower() in MISSING_TOKENS:
        return _missing(unit)

    is_percent = False
    if text.endswith("%"):
        is_percent = True
        text = text[:-1].strip()
    elif text.endswith("%)") and text.startswith("("):
        # (12.34%) 这类「括号 + 百分号」组合：去掉百分号，保留括号交给负号处理
        is_percent = True
        text = text[:-2] + ")"

    for name in sorted(UNIT_MULTIPLIERS, key=len, reverse=True):
        if text.endswith(name):
            unit = name
            text = text[: -len(name)].strip()
            break

    text = text.replace("￥", "").replace("¥", "").strip()

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.startswith("-"):
        negative = not negative
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()

    text = text.replace(",", "")
    if not _NUMBER.match(text):
        raise AppError(
            ErrorCode.PARSE_FAILED,
            "数值无法解析",
            {"raw": raw, "unit_hint": unit_hint},
        )

    value = Decimal(text)
    if negative:
        value = -value

    if is_percent:
        return NormalizedNumber(value=value, unit="%", is_missing=False)
    return NormalizedNumber(value=value * UNIT_MULTIPLIERS[unit], unit="元", is_missing=False)
