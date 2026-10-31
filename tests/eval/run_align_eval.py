"""科目对齐评估：黄金集 100 条（真实标签 60 + 变体 25 + 负样本 15）。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_align_eval.py
准确率 < 95% 或存在误配返回非 0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from align import match_label  # noqa: E402
from schema import load_accounts  # noqa: E402

GOLD = Path(__file__).resolve().parent / "gold" / "align-100.json"
THRESHOLD = 0.85


def main() -> int:
    schema = load_accounts()
    cases = json.loads(GOLD.read_text(encoding="utf-8"))
    stats = {"total": len(cases), "correct": 0}
    mismatches: list[str] = []
    false_positive = 0
    by_source: dict[str, list[int]] = {}

    for case in cases:
        match = match_label(
            case["raw"],
            page=case.get("page", 0),
            statement=case["statement"],
            schema=schema,
            threshold=THRESHOLD,
        )
        actual = match.account_code
        expected = case["expected"]
        ok = actual == expected
        bucket = by_source.setdefault(str(case["source"]), [0, 0])
        bucket[0] += 1
        if ok:
            stats["correct"] += 1
            bucket[1] += 1
        else:
            mismatches.append(
                f"{case['source']}: {case['raw']!r} 期望 {expected} 实际 {actual} ({match.reason})"
            )
            if expected is None:
                false_positive += 1

    accuracy = stats["correct"] / stats["total"]
    print(f"对齐用例：{stats['total']} 条，阈值 {THRESHOLD}")
    for source, (total, hit) in sorted(by_source.items()):
        print(f"  {source:<9} {hit}/{total}")
    print(f"准确率：{accuracy:.1%}（目标 ≥95%），负样本误配 {false_positive} 条")
    if mismatches:
        print("不一致明细：")
        for line in mismatches[:15]:
            print("  -", line)
    return 0 if accuracy >= 0.95 and false_positive == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
