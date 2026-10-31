import pytest

from parse.locate import (
    build_ranges,
    detect_start_pages,
    find_heading,
    is_statement_page,
    locate_statements,
    normalize,
)


def _income_page(extra: str = "") -> str:
    return (
        "合并利润表 单位：元 项目 2024年度 2023年度 一、营业总收入 23,343,093,018.69 "
        "19,650,329,209.04 其中：营业收入 23,343,093,018.69 减：营业成本 15,000,000,000.00 "
        + extra
    )


def _balance_page() -> str:
    return (
        "合并资产负债表 编制单位：示例公司 单位：元 项目 期末余额 期初余额 "
        "流动资产：货币资金 3,387,380,425.36 3,562,635,256.73 资产总计 10,000,000,000.00 "
        "负债合计 4,000,000,000.00 所有者权益合计 6,000,000,000.00"
    )


def _cashflow_page() -> str:
    return (
        "合并现金流量表 单位：元 项目 2024年度 2023年度 一、经营活动产生的现金流量："
        "销售商品、提供劳务收到的现金 22,908,708,903.11 19,036,092,030.17 "
        "经营活动产生的现金流量净额 4,000,000,000.00"
    )


def test_normalize_removes_all_whitespace():
    assert normalize("合并\n利润表 单位：元\u3000项目") == "合并利润表单位：元项目"


def test_heading_ignores_parent_company_page():
    page = _income_page().replace("合并利润表", "母公司利润表")
    assert find_heading(normalize(page), "income") is None
    assert is_statement_page(page, "income") is False


def test_toc_page_is_rejected():
    page = "目录 第一节 重要提示 合并利润表 119 合并资产负债表 114 合并现金流量表 122"
    assert is_statement_page(page, "income") is False


def test_management_analysis_table_is_rejected():
    page = (
        "利润表及现金流量表相关科目变动分析表 单位：元 科目 本期数 上年同期数 变动比例 "
        "营业收入 67,000,000,000.00 45,000,000,000.00 48.9"
    )
    assert is_statement_page(page, "income") is False


def test_statement_page_is_accepted():
    assert is_statement_page(_income_page(), "income") is True
    assert is_statement_page(_balance_page(), "balance") is True
    assert is_statement_page(_cashflow_page(), "cashflow") is True


def test_heading_only_page_with_continuation_is_accepted():
    heading_only = "3、合并利润表 单位：元" + "项目2024年度2023年度" * 4
    continuation = "一、营业总收入 23,343,093,018.69 减：营业成本 15,000,000,000.00"
    assert is_statement_page(heading_only, "income", continuation) is True
    assert is_statement_page(heading_only, "income") is False


def test_numeric_density_fallback_without_unit_marker():
    page = "合并利润表 " + "营业收入 1,234,567.89 " * 12
    assert is_statement_page(page, "income") is True


def test_detect_start_pages_and_ranges():
    pages = [
        "封面",
        _balance_page(),
        _income_page(),
        _cashflow_page(),
        "合并所有者权益变动表 单位：元 项目 实收资本 资本公积",
        "合并现金流量表补充资料 单位：元",
    ]
    starts = detect_start_pages(pages)
    assert starts == {"income": 3, "balance": 2, "cashflow": 4}

    located = locate_statements(pages)
    assert located.balance.start == 2 and located.balance.end == 2
    assert located.income.start == 3 and located.income.end == 3
    assert located.cashflow.start == 4
    assert located.cashflow.end == 4


def test_build_ranges_raises_when_missing():
    from core.errors import AppError, ErrorCode

    with pytest.raises(AppError) as exc_info:
        build_ranges({"income": 3, "balance": None, "cashflow": 4}, page_count=10)
    assert exc_info.value.code == ErrorCode.STATEMENT_LOCATE_FAILED
