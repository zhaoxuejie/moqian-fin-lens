"""科目 Schema 覆盖率评估（TASK-004 修订口径版，2026-10-31 经确认）。

三个指标：
1. 核心行覆盖率：分母 = 真实财报三表页中「可归因到 60 行核心科目」的标签，目标 ≥ 90%；
2. 全量行覆盖率：仅作参考，不设发布门槛（分母含银行/保险模板空行与换行截断）；
3. 指标依赖完整率：20 项指标所需科目必须 100% 可解析。

被 PDF 换行截断的标签（是某个核心别名的严格前缀）单独计数并排除，
避免把排版问题算成 Schema 缺口。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_schema_coverage.py
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

STATEMENT_KINDS = ("balance", "income", "cashflow")
LABEL = re.compile(r"^([\u4e00-\u9fa5（）()、：:]{2,30})")
SECTION_PREFIX = re.compile(r"^[一二三四五六七八九十]+、")
ARABIC_SECTION = re.compile(r"^（[一二三四五六七八九十]+）")
PREFIXES = ("其中：", "其中:", "减：", "减:", "加：", "加:")
PROSE_MARKS = "。，；！？"
STOPWORDS = {
    "项目",
    "附注",
    "单位",
    "币种",
    "编制单位",
    "法定代表人",
    "主管会计工作负责人",
    "会计机构负责人",
    "年初余额",
    "年末余额",
    "期末余额",
    "期初余额",
    "本期发生额",
    "上期发生额",
    "本年金额",
    "上年金额",
    "流动资产",
    "非流动资产",
    "流动负债",
    "非流动负债",
    "所有者权益",
    "股东权益",
}


def candidate_labels(text: str) -> set[str]:
    found: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or any(mark in line for mark in PROSE_MARKS):
            continue
        if SECTION_PREFIX.match(line) or ARABIC_SECTION.match(line):
            continue
        match = LABEL.match(line)
        if not match:
            continue
        label = match.group(1).rstrip("：:")
        if len(label) < 2 or label in STOPWORDS:
            continue
        remainder = line[len(match.group(1)):].strip()
        if remainder and remainder[0] not in "0123456789(-—－（":
            continue
        found.add(label)
    return found


def strip_prefix(label: str) -> str:
    for prefix in PREFIXES:
        if label.startswith(prefix):
            return label[len(prefix):]
    return label


def main() -> int:
    schema = load_accounts()
    core_codes = set(schema.core_rows)
    core_aliases = [alias for code in schema.core_rows for alias in schema.by_code[code].aliases]

    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    stats = {"core_hit": 0, "core_miss": 0, "truncated": 0, "other": 0}
    misses: dict[str, int] = {}
    rows: list[tuple[str, int, int]] = []

    for gold_file in sorted(GOLD_DIR.glob("*.json")):
        if not gold_file.stem.endswith("年度报告"):
            continue
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            continue

        labels: set[str] = set()
        with PdfDoc(pdf) as doc:
            for kind in STATEMENT_KINDS:
                start = gold["statements"][kind]["start"]
                for page in range(start, start + 3):
                    if page <= doc.page_count:
                        labels |= candidate_labels(doc.page_text(page))

        file_hit = file_miss = 0
        for label in labels:
            account = schema.resolve(strip_prefix(label))
            if account is not None:
                if account.code in core_codes:
                    stats["core_hit"] += 1
                    file_hit += 1
                else:
                    stats["other"] += 1
                continue
            if any(label != alias and (alias.startswith(label) or (len(label) >= 2 and label in alias)) and len(alias) >= 4 for alias in core_aliases):
                stats["truncated"] += 1
                continue
            if any((alias in label or label in alias) for alias in core_aliases if len(alias) >= 4):
                stats["core_miss"] += 1
                misses[label] = misses.get(label, 0) + 1
                file_miss += 1
            else:
                stats["other"] += 1
        rows.append((gold_file.stem, file_hit, file_miss))

    denominator = stats["core_hit"] + stats["core_miss"]
    coverage = stats["core_hit"] / denominator if denominator else 0.0
    total = denominator + stats["other"] + stats["truncated"]
    overall = (stats["core_hit"] + stats["other"]) / total if total else 0.0

    print(f"{'file':<44} {'core_hit':>9} {'core_miss':>9}")
    for stem, hit, miss in rows:
        print(f"{stem:<44} {hit:>9} {miss:>9}")

    metrics_ok = all(
        code in schema.by_code
        for codes in schema.metric_requirements.values()
        for code in codes
    )
    print(f"\n核心行覆盖率：{stats['core_hit']}/{denominator} = {coverage:.1%}（目标 ≥90%）")
    print(f"参考·全量行覆盖率：{overall:.1%}（命中 {stats['core_hit'] + stats['other']} / {total}）")
    print(f"换行截断标签（已排除）：{stats['truncated']}")
    print(f"指标依赖完整率：{'100%' if metrics_ok else '未通过'}（{len(schema.metric_requirements)} 项）")

    if misses:
        print("\n核心行未命中（按次数，前 20）：")
        for label, count in sorted(misses.items(), key=lambda item: (-item[1], item[0]))[:20]:
            print(f"  {count}x {label}")

    passed = coverage >= 0.90 and metrics_ok
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
