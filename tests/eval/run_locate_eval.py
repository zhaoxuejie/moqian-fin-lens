"""对比 parse.locate 与金标（tests/eval/gold），输出逐份结果与准确率。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_locate_eval.py
不达标（任一三表起始页偏差 > 2 页）返回非 0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import PdfDoc, locate_statements  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
KINDS = ("income", "balance", "cashflow")
TOLERANCE = 2


def main() -> int:
    gold_files = sorted(GOLD_DIR.glob("*.json"))
    if not gold_files:
        print("未找到金标，请先运行 tests/eval/build_gold.py")
        return 2

    total = 0
    passed = 0
    failures: list[str] = []
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    print(f"{'file':<44} {'income':>12} {'balance':>12} {'cashflow':>12}")
    for gold_file in gold_files:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        stem = gold_file.stem
        pdf = pdf_index.get(stem)
        if pdf is None:
            print(f"{stem:<44} MISSING PDF")
            failures.append(f"{stem}: 缺少 PDF")
            continue

        with PdfDoc(pdf) as doc:
            pages = [doc.page_text(i) for i in range(1, doc.page_count + 1)]
        located = locate_statements(pages)

        cells = []
        for kind in KINDS:
            expected = gold["statements"][kind]["start"]
            actual = getattr(located, kind).start
            ok = expected is not None and abs(actual - expected) <= TOLERANCE
            cells.append(f"{actual}/{expected}{'' if ok else '!'}")
            total += 1
            if ok:
                passed += 1
            else:
                failures.append(f"{stem}:{kind} 实际 {actual} 金标 {expected}")
        print(f"{stem:<44} {cells[0]:>12} {cells[1]:>12} {cells[2]:>12}")

    accuracy = passed / total if total else 0.0
    print(f"\n三表定位：{passed}/{total}，准确率 {accuracy:.1%}（容差 ±{TOLERANCE} 页）")
    if failures:
        print("失败明细：")
        for item in failures:
            print("  -", item)
    return 0 if total > 0 and passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
