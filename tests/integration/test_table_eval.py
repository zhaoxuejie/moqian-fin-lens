import json
import time
from decimal import Decimal
from pathlib import Path

import pytest

from align import normalize_label
from parse.normalize import normalize
from parse.table import extract_statement_rows

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
GOLD_FILE = GOLD_DIR / "table-200.json"

TOLERANCE = 0.95


def _canonical(label: str) -> str:
    return normalize_label(label).replace("(损失)", "").replace("（损失）", "")


def _load_cases():
    if not GOLD_FILE.exists():
        pytest.skip("表格金标不存在")
    return json.loads(GOLD_FILE.read_text(encoding="utf-8"))


def test_table_rows_meet_accuracy_target():
    cases = _load_cases()
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    statement_gold = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in GOLD_DIR.glob("*年度报告.json")
    }

    by_report: dict[str, list[dict]] = {}
    for case in cases:
        by_report.setdefault(case["report"], []).append(case)

    matched = total = 0
    for report, report_cases in by_report.items():
        pdf = pdf_index.get(report)
        if pdf is None:
            continue
        gold = statement_gold[report]
        ranges = {
            kind: (gold["statements"][kind]["start"], gold["statements"][kind]["start"] + 2)
            for kind in ("income", "balance", "cashflow")
        }
        rows = extract_statement_rows(str(pdf), ranges)
        index: dict[tuple[int, str], list] = {}
        for kind_rows in rows.values():
            for row in kind_rows:
                index.setdefault((row.page, _canonical(row.label)), []).append(row)

        for case in report_cases:
            total += 1
            candidates = index.get((case["page"], _canonical(case["label"])), [])
            if not candidates:
                continue
            actual = {cell.period: cell.value for cell in candidates[0].cells}
            expected = normalize(case["current"]).value
            if actual.get("current") == expected:
                matched += 1

    assert total >= 200
    assert matched / total >= TOLERANCE


def test_statement_extraction_performance():
    pdf = next((PDF_DIR / "002475_立讯精密").glob("*2025*.pdf"))
    if not pdf.exists():
        pytest.skip("缺少评估集 PDF")
    gold = json.loads((GOLD_DIR / "002475_立讯精密_2025年年度报告.json").read_text(encoding="utf-8"))
    ranges = {
        kind: (gold["statements"][kind]["start"], gold["statements"][kind]["start"] + 2)
        for kind in ("income", "balance", "cashflow")
    }
    started = time.perf_counter()
    rows = extract_statement_rows(str(pdf), ranges)
    elapsed = time.perf_counter() - started

    assert sum(len(items) for items in rows.values()) > 100
    assert elapsed < 60
def test_cross_page_rows_have_page_and_snippet():
    gold = json.loads((GOLD_DIR / "002230_科大讯飞_2024年年度报告.json").read_text(encoding="utf-8"))
    pdf = next((PDF_DIR / "002230_科大讯飞").glob("*2024*.pdf"))
    if not pdf.exists():
        pytest.skip("缺少评估集 PDF")
    start = gold["statements"]["balance"]["start"]
    rows = extract_statement_rows(str(pdf), {"balance": (start, start + 4)})["balance"]

    assert rows, "资产负债表应还原出行"
    for row in rows:
        assert row.page >= 1
        assert row.snippet
    pages = {row.page for row in rows}
    assert len(pages) >= 3, f"跨页表应覆盖多页，实际 {sorted(pages)}"

    keys = [(row.page, _canonical(row.label)) for row in rows if row.label]
    duplicates = len(keys) - len(set(keys))
    assert duplicates <= 5, f"疑似重复行过多：{duplicates}"
