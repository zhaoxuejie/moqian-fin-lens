"""指标计算评估：20 项 × 10 份年报 = 200 个值，与金标逐项比较。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_metrics_eval.py
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from metrics import check_statements, compute_metrics, values_from_rows  # noqa: E402
from parse.table import extract_statement_rows  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
GOLD_FILE = GOLD_DIR / "metrics-200.json"


def main() -> int:
    cases = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    statement_gold = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in GOLD_DIR.glob("*年度报告.json")
    }

    by_report: dict[str, list[dict]] = {}
    for case in cases:
        by_report.setdefault(case["report"], []).append(case)

    matched = total = 0
    mismatches: list[str] = []
    check_stats: dict[str, int] = {}

    for report, report_cases in by_report.items():
        pdf = pdf_index.get(report)
        if pdf is None:
            continue
        gold = statement_gold[report]
        starts = {kind: gold["statements"][kind]["start"] for kind in ("income", "balance", "cashflow")}
        ordered = sorted(starts.values())
        ranges = {
            kind: (starts[kind], (ordered[ordered.index(starts[kind]) + 1] - 1) if ordered.index(starts[kind]) + 1 < len(ordered) else starts[kind] + 2)
            for kind in ("income", "balance", "cashflow")
        }
        rows = extract_statement_rows(str(pdf), ranges)
        values = values_from_rows(rows)
        results = {item.code: item for item in compute_metrics(values)}

        for check in check_statements(values):
            check_stats[check.status] = check_stats.get(check.status, 0) + 1

        for case in report_cases:
            total += 1
            result = results.get(case["code"])
            actual = None if result is None or result.value is None else result.value
            expected = None if case["expected"] is None else Decimal(case["expected"])
            if actual == expected:
                matched += 1
            else:
                mismatches.append(
                    f"{report} {case['code']} 期望 {case['expected']} 实际 {actual}"
                )

    accuracy = matched / total if total else 0.0
    print(f"指标一致：{matched}/{total} = {accuracy:.1%}（目标 100%）")
    print(f"勾稽状态分布：{check_stats}")
    if mismatches:
        print("不一致样例（前 15）：")
        for line in mismatches[:15]:
            print("  -", line)
    return 0 if accuracy == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
