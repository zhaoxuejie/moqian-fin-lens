"""生成「行-值」金标（data/gold/table-200.json → tests/eval/gold/）。

金标来源：三表页原始文本行（正则：科目名 + 两个金额），与表格还原（坐标聚类）
属于两条不同路径，用于交叉校验。每份年报取 20 行，共 200 行。

用法：
    .venv\\Scripts\\python.exe tests/eval/build_table_gold.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import PdfDoc  # noqa: E402
from schema import load_accounts  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"
OUT_FILE = OUT_DIR / "table-200.json"

ROW = re.compile(
    r"^(?P<label>[\u4e00-\u9fa5（）()、：:]{2,30}?)\s+"
    r"(?:(?P<note>[^\s]+)\s+)?"
    r"(?P<current>\(?-?[\d,]{5,}(?:\.\d{2})?\)?)\s+"
    r"(?P<previous>\(?-?[\d,]{5,}(?:\.\d{2})?\)?)\s*$"
)
PER_REPORT = 20


def main() -> int:
    schema = load_accounts()
    cases: list[dict[str, object]] = []
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}

    for gold_file in sorted(GOLD_DIR.glob("*年度报告.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            continue
        picked = 0
        with PdfDoc(pdf) as doc:
            for kind in ("income", "balance", "cashflow"):
                start = gold["statements"][kind]["start"]
                for page in range(start, start + 4):
                    if page > doc.page_count or picked >= PER_REPORT:
                        continue
                    for line in doc.page_text(page).splitlines():
                        match = ROW.match(line.strip())
                        if not match:
                            continue
                        label = match.group("label").strip("：: ")
                        if len(label) < 2 or "。" in label or "，" in label:
                            continue

                        cases.append(
                            {
                                "report": gold_file.stem,
                                "statement": kind,
                                "page": page,
                                "label": label,
                                "current": match.group("current"),
                                "previous": match.group("previous"),
                                "source": "line-based",
                            }
                        )
                        picked += 1
                        if picked >= PER_REPORT:
                            break

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"共 {len(cases)} 行，写入 {OUT_FILE}")
    return 0 if len(cases) == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
