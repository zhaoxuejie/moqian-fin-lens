from decimal import Decimal

import pytest

from core.errors import AppError, ErrorCode
from parse import normalize


def D(value: str) -> Decimal:
    return Decimal(value)


@pytest.mark.parametrize(
    ("raw", "hint", "expected", "unit"),
    [
        ("1,234.56", None, D("1234.56"), "元"),
        ("1，234．56", None, D("1234.56"), "元"),
        ("１２３", None, D("123"), "元"),
        ("(1,234.00)", None, D("-1234.00"), "元"),
        ("（1,234.00）", None, D("-1234.00"), "元"),
        ("－1,234", None, D("-1234"), "元"),
        ("-1,234", None, D("-1234"), "元"),
        ("+1,000", None, D("1000"), "元"),
        ("￥1,000", None, D("1000"), "元"),
        ("¥1,000", None, D("1000"), "元"),
        ("1,000元", None, D("1000"), "元"),
        ("1.2万元", None, D("12000.0"), "元"),
        ("1.2 亿元", None, D("120000000.0"), "元"),
        ("3,000千元", None, D("3000000"), "元"),
        ("5百万元", None, D("5000000"), "元"),
        ("0", None, D("0"), "元"),
        ("0.00", None, D("0.00"), "元"),
        ("12.34%", None, D("12.34"), "%"),
        ("12.34％", None, D("12.34"), "%"),
        ("(12.34%)", None, D("-12.34"), "%"),
        ("1,234.56", "千元", D("1234560"), "元"),
        ("1,234.56", "万元", D("12345600"), "元"),
        ("1,234.56", "亿元", D("123456000000"), "元"),
        ("(1,000)", "万元", D("-10000000"), "元"),
        ("1,234", "元", D("1234"), "元"),
        ("0.0001", "万元", D("1.0000"), "元"),
        ("-0.00", None, D("0.00"), "元"),
        ("  1,234  ", None, D("1234"), "元"),
        ("1,234.5", None, D("1234.5"), "元"),
        ("12,345,678.90", None, D("12345678.90"), "元"),
        ("(0.00)", None, D("0.00"), "元"),
        ("1亿元", "万元", D("100000000"), "元"),
        ("2,000千元", "元", D("2000000"), "元"),
        ("100%", None, D("100"), "%"),
        ("0.5%", None, D("0.5"), "%"),
    ],
)
def test_normalize_numeric_values(raw: str, hint: str | None, expected: Decimal, unit: str):
    result = normalize(raw, hint)
    assert result.is_missing is False
    assert result.value == expected
    assert result.unit == unit


@pytest.mark.parametrize(
    "raw",
    ["", " ", "—", "——", "–", "-", "--", "－", "不适用", "无", "n/a", "N/A", "null", "/", None],
)
def test_missing_tokens_are_not_zero(raw: str | None):
    result = normalize(raw)
    assert result.is_missing is True
    assert result.value is None


def test_zero_is_not_missing():
    result = normalize("0")
    assert result.is_missing is False
    assert result.value == Decimal("0")


@pytest.mark.parametrize("raw", ["abc", "1.2.3", "1,2,3.4.5", "十二", "1 234"])
def test_invalid_text_raises(raw: str):
    with pytest.raises(AppError) as exc_info:
        normalize(raw)
    assert exc_info.value.code == ErrorCode.PARSE_FAILED
    assert exc_info.value.detail["raw"] == raw


def test_unknown_unit_hint_raises():
    with pytest.raises(AppError) as exc_info:
        normalize("1", "块")
    assert exc_info.value.code == ErrorCode.INVALID_PARAMS


def test_inline_unit_wins_over_hint():
    assert normalize("1万元", "亿元").value == Decimal("10000")
    assert normalize("1万元", "亿元").unit == "元"


def test_result_is_repeatable():
    first = normalize("(1,234.56)", "万元")
    second = normalize("(1,234.56)", "万元")
    assert first == second


def test_as_dict_is_json_friendly():
    payload = normalize("1.2亿元").as_dict()
    assert payload == {"value": "120000000.0", "unit": "元", "is_missing": False}
    assert normalize("—").as_dict() == {"value": None, "unit": "元", "is_missing": True}
