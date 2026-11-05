"""TASK-024 交叉核对断言：「主要会计数据」营业收入读取与「原文未披露」核对。"""

import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from run_crosscheck_eval import (  # noqa: E402
    account_lines,
    check_missing,
    check_revenue,
    read_main_revenue,
    to_yuan,
)

D = Decimal
RANGES = {"income": (3, 3), "balance": (4, 4), "cashflow": (5, 5)}


def _pages(section: str, balance: str = "合并资产负债表") -> list[str]:
    return ["封面", section, "合并利润表", balance, "合并现金流量表"]


# ---------- 断言 A：读「主要会计数据」 ----------


@pytest.mark.parametrize(
    ("section", "current", "previous", "unit"),
    [
        ("六、主要会计数据和财务指标\n单位：元 币种：人民币\n营业收入 1,000.00 800.00 25.00", D("1000.00"), D("800.00"), "元"),
        ("主要会计数据\n营业收入（元） 1,000.00 800.00 25.00%", D("1000.00"), D("800.00"), "元"),
        ("主要会计数据\n营业收入 （元） 1,000.00 800.00 25.00%", D("1000.00"), D("800.00"), "元"),
        ("主要会计数据\n单位：千元 币种：人民币\n营业收入 57,795,570 45,250,425 27.72", D("57795570000"), D("45250425000"), "千元"),
        ("主要会计数据\n营业收入（千元） 57,795,570 45,250,425 27.72", D("57795570000"), D("45250425000"), "千元"),
        ("主要会计数据\n营业总收入 2,000.00 1,500.00 33.33", D("2000.00"), D("1500.00"), "元"),
    ],
)
def test_read_main_revenue_formats(section, current, previous, unit):
    main, reason = read_main_revenue(_pages(section), before=3)
    assert reason is None
    assert (main.current, main.previous, main.unit, main.page) == (current, previous, unit, 2)
    assert not main.restated


def test_restated_report_uses_adjusted_previous_year():
    section = (
        "六、主要会计数据和财务指标\n公司是否需追溯调整或重述以前年度会计数据\n√ 是 □ 否\n"
        "2024 年 2023 年 本年比上年增减 2022 年\n调整前 调整后 调整后 调整前 调整后\n"
        "营业收入（元） 92,495,525,118.30 89,339,856,855.68 89,341,177,610.40 3.53% 83,166,321,681.14"
    )
    main, _ = read_main_revenue(_pages(section), before=3)
    assert main.restated
    assert main.previous == D("89341177610.40")
    assert main.raw == ("92,495,525,118.30", "89,341,177,610.40")


def test_not_restated_when_box_is_no():
    section = "主要会计数据\n公司是否需追溯调整或重述以前年度会计数据\n□ 是 √ 否\n营业收入（元） 100.00 80.00 25.00%"
    main, _ = read_main_revenue(_pages(section), before=3)
    assert not main.restated and main.previous == D("80.00")


def test_section_may_continue_on_next_page():
    pages = ["主要会计数据\n公司是否需追溯调整 □ 是 √ 否", "营业收入（元） 100.00 80.00 25.00%", "合并利润表"]
    main, _ = read_main_revenue(pages, before=3)
    assert main.page == 2 and main.current == D("100.00")


@pytest.mark.parametrize(
    ("pages", "before", "reason"),
    [
        (["封面", "目录", "合并利润表\n营业收入 1.00 2.00"], 3, "没有「主要会计数据」"),
        (["主要会计数据\n营业收入同比增长 23%，主要是…\n营业收入 增长 23%", "合并利润表"], 2, "没有带金额的营业收入行"),
        (["封面", "合并利润表", "主要会计数据\n营业收入 1.00 2.00"], 2, "没有「主要会计数据」"),
    ],
)
def test_read_main_revenue_reports_reason_instead_of_guessing(pages, before, reason):
    main, why = read_main_revenue(pages, before=before)
    assert main is None and reason in why


def test_check_revenue_statuses():
    pages = _pages("主要会计数据\n单位：千元\n营业收入 57,795,570 45,250,425 27.72")
    right = {"income": {"revenue": {"current": D("57795570000"), "previous": D("45250425000")}}}
    wrong = {"income": {"revenue": {"current": D("57795570"), "previous": D("45250425")}}}
    assert check_revenue(right, pages, RANGES).status == "一致"
    result = check_revenue(wrong, pages, RANGES)
    assert result.status == "不一致"
    assert "P.2" in result.detail and "57,795,570" in result.detail and "57795570 / 45250425" in result.detail
    assert check_revenue(right, _pages("目录"), RANGES).status == "未核对"


def test_to_yuan_handles_negative_forms():
    assert to_yuan("(1,234.50)", "元") == D("-1234.50")
    assert to_yuan("-12", "万元") == D("-120000")


# ---------- 断言 B：「原文未披露」核对 ----------


def _metric(code: str, reason: str | None, value=None):
    return SimpleNamespace(code=code, value=value, missing_reason=reason)


@pytest.mark.parametrize(
    ("balance", "kind"),
    [
        ("短期借款 七、32 1,161,359,197.75 1,000.00", "amount"),
        ("其中：短期借款 1,000.00 900.00", "amount"),
        ("商誉 - -", "empty"),
        ("其中：数据资源 - - 商誉 - - 长期待摊费用 - -", "empty"),
    ],
)
def test_account_lines(balance, kind):
    hits = list(account_lines({"短期借款", "商誉"}, _pages("", balance), RANGES))
    assert [(page, found) for page, found, _ in hits] == [(4, kind)]


def test_account_lines_ignores_other_accounts_and_pages_outside_ranges():
    pages = _pages("短期借款 1,000.00 900.00", "一年内到期的长期借款 1,000.00 900.00")
    assert list(account_lines({"短期借款", "长期借款"}, pages, RANGES)) == []


def test_check_missing_classifies_each_account():
    balance = "短期借款 1,000.00 900.00\n商誉 - -"
    metrics = [
        _metric("interest_bearing_debt", "原文未披露：short_term_borrowings、long_term_borrowings"),
        _metric("goodwill", "原文未披露：goodwill"),
        _metric("roe", None, D("12")),
        _metric("revenue_growth", "基期数据缺失"),
    ]
    results = check_missing(metrics, _pages("", balance), RANGES)
    assert [(item.metric, item.account, item.status) for item in results] == [
        ("interest_bearing_debt", "short_term_borrowings", "违反"),
        ("interest_bearing_debt", "long_term_borrowings", "通过"),
        ("goodwill", "goodwill", "列示为空"),
    ]
    assert results[0].evidence == ("P.4 短期借款 1,000.00 900.00",)
