"""数值归一交叉校验：100 个真实财报数字 vs 金标（tests/eval/gold/numbers-100.json）。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_numbers_eval.py
全部一致返回 0；任一不一致返回 1 并打印明细。
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import normalize  # noqa: E402

GOLD = Path(__file__).resolve().parent / "gold" / "numbers-100.json"


def main() -> int:
    samples = json.loads(GOLD.read_text(encoding="utf-8"))
    failures: list[tuple[dict[str, str], str]] = []

    for sample in samples:
        result = normalize(sample["raw"], sample["unit_hint"])
        expected = Decimal(sample["expected"])
        if result.is_missing or result.value != expected or result.unit != "元":
            failures.append((sample, result.as_dict()["value"] or "missing"))

    total = len(samples)
    passed = total - len(failures)
    print(f"数值归一：{passed}/{total}，一致率 {passed / total:.1%}")
    if failures:
        print("不一致明细（前 10 条）：")
        for sample, actual in failures[:10]:
            print(
                f"  raw={sample['raw']!r} hint={sample['unit_hint']} "
                f"expected={sample['expected']} actual={actual} @{sample['source']}"
            )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
