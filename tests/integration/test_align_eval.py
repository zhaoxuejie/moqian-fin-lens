import json
from pathlib import Path

import pytest

from align import align_entries, split_unaligned
from parse import PdfDoc
from parse.labels import extract_labels
from schema import load_accounts

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"

SCHEMA = load_accounts()
ALIGN_GOLD = GOLD_DIR / "align-100.json"


@pytest.mark.skipif(not ALIGN_GOLD.exists(), reason="对齐黄金集不存在")
def test_align_accuracy_meets_target():
    from align import match_label

    cases = json.loads(ALIGN_GOLD.read_text(encoding="utf-8"))
    correct = 0
    false_positive = 0
    for case in cases:
        match = match_label(
            case["raw"],
            page=case.get("page", 0),
            statement=case["statement"],
            schema=SCHEMA,
            threshold=0.85,
        )
        if match.account_code == case["expected"]:
            correct += 1
        elif case["expected"] is None:
            false_positive += 1
    assert correct / len(cases) >= 0.95
    assert false_positive == 0


def test_section_header_is_not_forced_into_account():
    matches = align_entries(
        [(122, "cashflow", "经营活动产生的现金流量：")],
        schema=SCHEMA,
    )
    assert matches[0].aligned is False
    assert matches[0].reason == "section_header"


def test_real_report_unaligned_items_keep_page_numbers():
    gold = json.loads(
        (GOLD_DIR / "002230_科大讯飞_2024年年度报告.json").read_text(encoding="utf-8")
    )
    pdf = PDF_DIR / "002230_科大讯飞" / "002230_科大讯飞_2024年年度报告.pdf"
    if not pdf.exists():
        pytest.skip("缺少评估集 PDF")

    entries: list[tuple[int, str, str]] = []
    with PdfDoc(pdf) as doc:
        for kind in ("income", "balance", "cashflow"):
            start = gold["statements"][kind]["start"]
            for label in extract_labels(doc.page_text(start)):
                entries.append((start, kind, label))

    matches = align_entries(entries, schema=SCHEMA)
    aligned, unaligned = split_unaligned(matches)

    assert aligned, "真实报表页应当能对齐出至少一个科目"
    for item in unaligned:
        assert item.page >= 1
        assert item.raw_label
        assert item.account_code is None


def test_unaligned_entries_are_not_silently_dropped():
    entries = [
        (42, "income", "营业收入"),
        (42, "income", "＃＠乱码科目"),
        (119, "income", "合并利润表"),
    ]
    matches = align_entries(entries, schema=SCHEMA)
    aligned, unaligned = split_unaligned(matches)
    assert len(aligned) + len(unaligned) == len(entries)
    assert len(unaligned) == 2
    assert {item.raw_label for item in unaligned} == {"＃＠乱码科目", "合并利润表"}
