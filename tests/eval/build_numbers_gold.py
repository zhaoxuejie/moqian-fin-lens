"""从评估集真实财报中抽取 100 个原始数字，生成数值归一的交叉校验集。

用途：TASK-003 的「金标 100 个数字」验收项。
独立性说明：期望值由本脚本内另一套简化实现计算（字符串清洗 + Decimal + 单位倍数），
与 parse/normalize.py 的实现路径不同，但**不是人工标注**；如需更强证据，应人工抽检。

用法：
    .venv\\Scripts\\python.exe tests/eval/build_numbers_gold.py
输出：data/gold/numbers-100.json（再复制到 tests/eval/gold/）
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import PdfDoc  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"

FACTORS = {
    "元": Decimal(1),
    "千元": Decimal(1_000),
    "万元": Decimal(10_000),
    "亿元": Decimal(100_000_000),
}
UNIT_PATTERNS = [
    ("单位：千元", "千元"),
    ("单位:千元", "千元"),
    ("单位：万元", "万元"),
    ("单位:万元", "万元"),
    ("单位：亿元", "亿元"),
    ("单位：人民币元", "元"),
    ("单位:人民币元", "元"),
    ("单位：元", "元"),
    ("单位:元", "元"),
]
TOKEN = re.compile(r"(?<![\d.,])\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?(?![,\d])")
PER_COMPANY = 20


def independent_value(raw: str, unit: str) -> Decimal:
    text = raw.strip()
    negative = text.startswith("(")
    text = text.strip("()").replace(",", "")
    value = Decimal(text)
    if negative:
        value = -value
    return value * FACTORS[unit]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    samples: list[dict[str, object]] = []

    for gold_file in sorted(GOLD_DIR.glob("*.json")):
        if "2024" not in gold_file.stem:
            continue
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            continue

        with PdfDoc(pdf) as doc:
            page_texts = []
            for kind in ("balance", "income", "cashflow"):
                start = gold["statements"][kind]["start"]
                end = gold["statements"].get(kind, {}).get("end", start)
                for page in range(start, end + 1):
                    page_texts.append((page, doc.page_text(page)))

        picked = 0
        for page, text in page_texts:
            unit = "元"
            for pattern, name in UNIT_PATTERNS:
                if pattern in text:
                    unit = name
                    break
            for match in TOKEN.finditer(text):
                raw = match.group(0)
                if picked >= PER_COMPANY:
                    break
                samples.append(
                    {
                        "raw": raw,
                        "unit_hint": unit,
                        "expected": str(independent_value(raw, unit)),
                        "source": f"{gold_file.stem}:p{page}",
                    }
                )
                picked += 1
            if picked >= PER_COMPANY:
                break

        print(f"{gold_file.stem}: {picked} 个数字")

    out = OUT_DIR / "numbers-100.json"
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"合计 {len(samples)} 个，写入 {out}")
    return 0 if len(samples) >= 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
