"""生成 20 项指标金标（data/gold/metrics-200.json → tests/eval/gold/）。

独立路径：三表页原始文本行（正则）→ 科目值 → 指标公式，与产品侧
（pdfplumber 表格 → 行 → 指标）属于不同的抽取路径，用于交叉校验。

用法：
    .venv\\Scripts\\python.exe tests/eval/build_metrics_gold.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from align import normalize_label  # noqa: E402
from metrics import METRICS, compute_metrics  # noqa: E402
from parse import PdfDoc  # noqa: E402
from parse.normalize import normalize  # noqa: E402
from schema import load_accounts  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"
OUT_FILE = OUT_DIR / "metrics-200.json"

ROW = re.compile(
    r"^(?P<label>[\u4e00-\u9fa5（）()、：:]{2,30}?)\s+"
    r"(?:(?P<note>[^\s]+)\s+)?"
    r"(?P<current>\(?-?[\d,]{5,}(?:\.\d{2})?\)?)\s+"
    r"(?P<previous>\(?-?[\d,]{5,}(?:\.\d{2})?\)?)\s*$"
)
NUMBERING = re.compile(r"^[一二三四五六七八九十]+、")
NOTE = re.compile(r"[\(（](?:损失|[一二三四五六七八九十]+|\d+)[\)）]\d*$")


TRAILING_OPEN = re.compile(r"[\(（][^\)）]*$")


def canonical(label: str) -> str:
    value = NUMBERING.sub("", normalize_label(label))
    value = TRAILING_OPEN.sub("", value)
    return NOTE.sub("", value).strip()


def build_values(pages: list[str], schema) -> dict[str, dict[str, dict[str, str]]]:
    values: dict[str, dict[str, dict[str, str]]] = {}
    for text in pages:
        for line in text.splitlines():
            match = ROW.match(line.strip())
            if not match:
                continue
            label = canonical(match.group("label"))
            account = schema.resolve(label)
            if account is None:
                continue
            bucket = values.setdefault(account.statement, {}).setdefault(account.code, {})
            bucket.setdefault("current", match.group("current"))
            bucket.setdefault("previous", match.group("previous"))
    return values


def main() -> int:
    schema = load_accounts()
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    cases: list[dict[str, object]] = []

    for gold_file in sorted(GOLD_DIR.glob("*年度报告.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            continue
        pages: list[str] = []
        with PdfDoc(pdf) as doc:
            for kind in ("income", "balance", "cashflow"):
                start = gold["statements"][kind]["start"]
                for page in range(start, start + 4):
                    if page <= doc.page_count:
                        pages.append(doc.page_text(page))

        raw_values = build_values(pages, schema)
        values = {
            kind: {
                code: {period: normalize(text).value for period, text in periods.items()}
                for code, periods in codes.items()
            }
            for kind, codes in raw_values.items()
        }

        for result in compute_metrics(values, schema):
            cases.append(
                {
                    "report": gold_file.stem,
                    "code": result.code,
                    "expected": None if result.value is None else str(result.value),
                    "unit": result.unit,
                    "missing_reason": result.missing_reason,
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"共 {len(cases)} 项指标值，写入 {OUT_FILE}")
    return 0 if len(cases) == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
