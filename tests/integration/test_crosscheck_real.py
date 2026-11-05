"""TASK-024 在真实年报上的交叉核对，以及两条断言确实会变红。"""

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import dashboard.session as session  # noqa: E402
from metrics import compute_metrics, values_from_rows  # noqa: E402
from run_crosscheck_eval import (  # noqa: E402
    PDF_DIR,
    check_missing,
    check_revenue,
    period_of,
    read_pages,
    statement_ranges,
)
from schema import load_accounts  # noqa: E402


@pytest.fixture(scope="module")
def reports():
    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    if not pdfs:
        pytest.skip("缺少评估集 PDF")
    result = {}
    for pdf in pdfs:
        pages = read_pages(pdf)
        result[pdf.stem] = (pdf, session.build_filing(pdf, period_of(pdf)), pages, statement_ranges(pages))
    return result


def test_revenue_matches_main_accounting_data(reports):
    statuses = {}
    for name, (_pdf, filing, pages, ranges) in reports.items():
        result = check_revenue(filing.values, pages, ranges)
        statuses[name] = result
        assert result.status == "一致", f"{name}: {result.detail}"
    assert len(statuses) == 10
    restated = [name for name, result in statuses.items() if result.main.restated]
    assert restated == ["002415_海康威视_2024年年度报告"]


def test_missing_accounts_are_really_absent(reports):
    empties = []
    for name, (_pdf, filing, pages, ranges) in reports.items():
        for item in check_missing(filing.metrics, pages, ranges):
            assert item.status != "违反", f"{name} {item.metric} 缺 {item.account}: {item.evidence}"
            if item.status == "列示为空":
                empties.append((name, item.account))
    assert empties == [("688981_中芯国际_2024年年度报告", "goodwill"), ("688981_中芯国际_2025年年度报告", "goodwill")]


def test_assertion_a_catches_ignored_thousand_yuan_unit(reports, monkeypatch):
    """复现 v0.4.1：表头单位一律按元。"""
    monkeypatch.setattr(session, "statement_units", lambda pages, ranges: {kind: "元" for kind in ranges})
    failed = []
    for name, (pdf, _filing, pages, ranges) in reports.items():
        if "中芯国际" not in name:
            continue
        result = check_revenue(session.build_filing(pdf, period_of(pdf)).values, pages, ranges)
        assert result.status == "不一致"
        assert "P.8" in result.detail and "千元" in result.detail
        failed.append(name)
    assert len(failed) == 2


def test_assertion_b_catches_missing_alias(reports):
    """科目表里去掉三项借款的写法：有息负债会变成「原文未披露」，原文里却有金额行。"""
    schema = load_accounts()
    removed = {"短期借款", "长期借款", "应付债券"}
    broken = dataclasses.replace(
        schema, alias_index={alias: code for alias, code in schema.alias_index.items() if alias not in removed}
    )
    _pdf, filing, pages, ranges = reports["002415_海康威视_2024年年度报告"]
    metrics = compute_metrics(values_from_rows(filing.rows, broken))
    results = check_missing(metrics, pages, ranges)
    violations = {item.account: item for item in results if item.status == "违反"}
    assert set(violations) == {"short_term_borrowings", "long_term_borrowings"}
    assert all(evidence.startswith("P.") for item in violations.values() for evidence in item.evidence)
