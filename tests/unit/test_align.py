import pytest

from align import align_entries, match_label, normalize_label, split_unaligned
from core.config import Settings
from schema import load_accounts

SCHEMA = load_accounts()


def test_normalize_label_strips_prefix_and_unit_suffix():
    assert normalize_label("其中：营业收入") == "营业收入"
    assert normalize_label("减：营业成本（元）") == "营业成本"
    assert normalize_label(" 净利润（人民币元） ") == "净利润"
    assert normalize_label("资产总计：") == "资产总计"


def test_exact_alias_matches_with_full_confidence():
    match = match_label("营业总收入", page=42, statement="income", schema=SCHEMA)
    assert match.account_code == "revenue_total"
    assert match.source == "rule"
    assert match.confidence == 1.0
    assert match.aligned and not match.needs_review


def test_prefix_form_is_rule_matched():
    match = match_label("其中：营业收入", page=42, statement="income", schema=SCHEMA)
    assert match.account_code == "revenue"
    assert match.source == "rule"


def test_unit_suffix_is_rule_matched():
    match = match_label("经营活动产生的现金流量净额（元）", page=103, statement="cashflow", schema=SCHEMA)
    assert match.account_code == "ocf_net"


def test_fuzzy_fallback_returns_review_flag():
    match = match_label(
        "销售商品、提供劳务收到的现金（含税）",
        page=103,
        statement="cashflow",
        schema=SCHEMA,
        threshold=0.80,
    )
    assert match.aligned
    assert match.source == "fuzzy"
    assert 0.80 <= match.confidence < 1.0
    assert match.needs_review


def test_threshold_controls_fuzzy_matching():
    strict = match_label("应收帐款", page=87, statement="balance", schema=SCHEMA, threshold=0.99)
    loose = match_label("应收帐款", page=87, statement="balance", schema=SCHEMA, threshold=0.75)
    assert strict.source == "unaligned"
    assert loose.source == "fuzzy"
    assert loose.account_code == "accounts_receivable"


def test_unknown_label_stays_unaligned_with_page():
    match = match_label("合并利润表", page=119, statement="income", schema=SCHEMA)
    assert match.aligned is False
    assert match.source == "unaligned"
    assert match.reason == "no_match"
    assert match.page == 119
    assert match.raw_label == "合并利润表"


def test_statement_mismatch_is_not_forced():
    match = match_label("资产总计", page=42, statement="income", schema=SCHEMA)
    assert match.aligned is False
    assert match.reason == "statement_mismatch"


def test_one_label_maps_to_exactly_one_code():
    matches = align_entries(
        [(42, "income", "营业收入")] * 5,
        schema=SCHEMA,
    )
    codes = {item.account_code for item in matches}
    assert codes == {"revenue"}


def test_split_unaligned_keeps_pages():
    matches = align_entries(
        [
            (42, "income", "营业收入"),
            (119, "income", "合并利润表"),
            (114, "balance", "货币资金"),
        ],
        schema=SCHEMA,
    )
    aligned, unaligned = split_unaligned(matches)
    assert len(aligned) == 2
    assert len(unaligned) == 1
    assert unaligned[0].raw_label == "合并利润表"
    assert unaligned[0].page == 119


def test_threshold_comes_from_settings():
    settings = Settings(database_path="./data/app.db", align_confidence_threshold=0.9, _env_file=None)
    assert settings.align_confidence_threshold == 0.9
    match = match_label("应收帐款", page=87, statement="balance", schema=SCHEMA, threshold=0.9)
    assert match.source == "unaligned"
