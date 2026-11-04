"""表格还原评估：200 行金标 vs 坐标聚类还原结果。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_table_eval.py
一致率 < 95% 返回非 0。
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import re  # noqa: E402

from align import normalize_label  # noqa: E402
from parse.normalize import normalize  # noqa: E402
from parse import PdfDoc  # noqa: E402
from parse.table import extract_statement_rows, statement_units  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
GOLD_FILE = GOLD_DIR / "table-200.json"


NOTE = re.compile(r"[\(（](?:损失|[一二三四五六七八九十]+|\d+)[\)）]\d*$")


def canonical(label: str) -> str:
    return NOTE.sub("", normalize_label(label)).strip()


def _expected(raw: str, unit: str = "元") -> Decimal:
    result = normalize(raw, unit)
    assert result.value is not None
    return result.value


def _units(pdf: Path, ranges: dict[str, tuple[int, int]]) -> dict[str, str]:
    """与产品同一口径读各表表头单位（TASK-023）。"""
    with PdfDoc(str(pdf)) as doc:
        pages = [doc.page_text(number) for number in range(1, doc.page_count + 1)]
    return statement_units(pages, ranges)


def main() -> int:
    cases = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    statement_gold = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in GOLD_DIR.glob("*年度报告.json")
    }

    by_report: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        by_report.setdefault(str(case["report"]), []).append(case)

    total = matched = 0
    misses: list[str] = []
    for report, report_cases in sorted(by_report.items()):
        pdf = pdf_index.get(report)
        if pdf is None:
            continue
        gold = statement_gold[report]
        ranges = {
            kind: (gold["statements"][kind]["start"], gold["statements"][kind]["start"] + 2)
            for kind in ("income", "balance", "cashflow")
        }
        rows = extract_statement_rows(str(pdf), ranges, _units(pdf, ranges))
        index: dict[tuple[int, str], list] = {}
        for kind_rows in rows.values():
            for row in kind_rows:
                key = (row.page, canonical(row.label))
                index.setdefault(key, []).append(row)

        for case in report_cases:
            total += 1
            key = (int(case["page"]), canonical(str(case["label"])))
            candidates = index.get(key, [])
            if not candidates:
                misses.append(f"{report}:{case['page']} {case['label']} 未找到行")
                continue
            row = candidates[0]
            actual = {cell.period: cell.value for cell in row.cells}
            ok = actual.get("current") == _expected(str(case["current"]), case.get("unit", "元"))
            if ok and actual.get("previous") is not None:
                ok = actual["previous"] == _expected(str(case["previous"]), case.get("unit", "元"))
            if ok:
                matched += 1
            else:
                misses.append(
                    f"{report}:{case['page']} {case['label']} 期望 {case['current']} 实际 {actual.get('current')}"
                )

    accuracy = matched / total if total else 0.0
    print(f"行-值一致：{matched}/{total} = {accuracy:.1%}（目标 ≥95%）")
    if misses:
        print("未命中样例（前 15）：")
        for line in misses[:15]:
            print("  -", line)
    return 0 if accuracy >= 0.95 else 1


if __name__ == "__main__":
    raise SystemExit(main())
