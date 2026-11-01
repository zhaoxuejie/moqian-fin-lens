import pytest

from core.errors import AppError, ErrorCode
from dashboard.session import append_filing, company_key


def test_company_key_ignores_year_and_extension():
    assert company_key("002230_科大讯飞_2024年年度报告.pdf") == company_key("002230_科大讯飞_2025年年度报告.pdf")
    assert company_key("a.pdf") != company_key("b.pdf")


def test_append_filing_sorts_by_period(dashboard_session):
    from dataclasses import replace

    latest = dashboard_session.latest
    filing_2023 = replace(latest, period="2023", filing_id="f_02")
    merged = append_filing(dashboard_session, filing_2023)

    assert [item.period for item in merged.filings] == ["2023", "2024"]
    assert merged.session_id == dashboard_session.session_id


def test_append_filing_rejects_duplicate_period(dashboard_session):
    from dataclasses import replace

    duplicate = replace(dashboard_session.latest, filing_id="f_dup")
    with pytest.raises(AppError) as exc_info:
        append_filing(dashboard_session, duplicate)

    assert exc_info.value.code == ErrorCode.SESSION_MISMATCH
    assert exc_info.value.detail["reason"] == "duplicate_period"


def test_append_filing_rejects_when_full(dashboard_session):
    from dataclasses import replace

    session = dashboard_session
    for index, period in enumerate(["2020", "2021", "2022", "2023"], start=2):
        session = append_filing(session, replace(session.latest, period=period, filing_id=f"f{index}"))

    with pytest.raises(AppError) as exc_info:
        append_filing(session, replace(session.latest, period="2019", filing_id="f9"))

    assert exc_info.value.code == ErrorCode.SESSION_FULL

def test_session_yoy_uses_latest_and_previous_filing():
    from types import SimpleNamespace

    from dashboard.build import session_yoy
    from metrics import MetricResult

    def metric(label, value, unit):
        return MetricResult(code=label, label=label, value=value, unit=unit, formula="x")

    latest = SimpleNamespace(metrics=[metric("revenue_total", 120, "元"), metric("gross_margin", 30, "%")])
    previous = SimpleNamespace(metrics=[metric("revenue_total", 100, "元"), metric("gross_margin", 25, "%")])

    result = session_yoy([previous, latest])

    assert result["revenue_total"]["unit"] == "%"
    assert float(result["revenue_total"]["value"]) == 20.0
    assert result["gross_margin"]["unit"] == "pct"
    assert float(result["gross_margin"]["value"]) == 5


def test_session_yoy_skips_single_filing(dashboard_session):
    from dashboard.build import session_yoy

    assert session_yoy([dashboard_session.latest]) == {}

def test_filter_trims_previous_statement_tail():
    from dashboard.session import filter_rows_by_statement
    from parse.table import StatementRow

    rows = {
        "income": [
            StatementRow(label="所有者权益（或股东权益）合计", page=130, snippet="", cells=(), is_missing=True),
            StatementRow(label="一、营业总收入", page=130, snippet="", cells=(), is_missing=True),
        ]
    }
    filtered = filter_rows_by_statement(rows)
    assert filtered["income"][0].label == "一、营业总收入"

def test_extract_company_info_fields():
    from dashboard.session import _extract_company_info

    text = (
        "公司的中文名称 测试股份有限公司\n"
        "公司的外文名称（如有） TEST CO.,LTD\n"
        "公司的外文名称缩写（如有） TEST\n"
        "公司的法定代表人 张三\n"
        "公司网址 http://www.test.com 电子信箱 a@test.com\n"
        "注册地址 测试市测试路 1 号\n"
        "办公地址 测试市测试路 2 号"
    )
    info = _extract_company_info([text])

    assert info["全称"] == "测试股份有限公司"
    assert info["外文名称"] == "TEST CO.,LTD"
    assert info["外文缩写"] == "TEST"
    assert info["法定代表人"] == "张三"
    assert info["网址"] == "http://www.test.com"
    assert info["邮箱"] == "a@test.com"
    assert info["注册地址"] == "测试市测试路 1 号"
