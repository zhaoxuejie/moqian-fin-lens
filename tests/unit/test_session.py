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
