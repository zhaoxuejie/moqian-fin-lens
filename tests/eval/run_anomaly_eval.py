"""TASK-022 评测：异常项页码与 ROE 可算出份数（评估集 10 份年报）。

逐份构建 filing，检查：
1. 每条异常项 page_refs 至少 1 个；
2. 每个页码都等于某个证据科目在「单年报表」展示行里的溯源页码；
3. ROE（归母口径）可算出的份数。

用法：
    python tests/eval/run_anomaly_eval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from align import normalize_label  # noqa: E402
from anomaly.rules import RULE_ACCOUNTS  # noqa: E402
from dashboard.session import build_filing, filter_rows_by_statement  # noqa: E402
from metrics.compute import NUMBERING  # noqa: E402
from schema import load_accounts  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent / "pdf"


def displayed_pages(filing, schema) -> dict[tuple[str, str], set[int]]:
    """单年报表页展示的行：标准科目 → 该科目所在行的溯源页码集合。"""
    pages: dict[tuple[str, str], set[int]] = {}
    for kind, rows in filter_rows_by_statement(filing.rows).items():
        for row in rows:
            account = schema.resolve(NUMBERING.sub("", normalize_label(row.label)))
            if account is not None and row.cells:
                pages.setdefault((kind, account.code), set()).add(row.page)
    return pages


def main() -> int:
    schema = load_accounts()
    pdfs = sorted(PDF_DIR.rglob("*年度报告.pdf"))
    if not pdfs:
        print("缺少评估集 PDF")
        return 1

    total = with_pages = matched = roe_ok = 0
    for pdf in pdfs:
        period = pdf.stem.split("_")[2][:4]
        filing = build_filing(pdf, period)
        shown = displayed_pages(filing, schema)
        roe = filing.metrics_by_code["roe"]
        roe_ok += roe.value is not None
        print(f"{pdf.stem}  ROE={'%.2f' % roe.value if roe.value is not None else roe.missing_reason}")
        for item in filing.anomalies:
            total += 1
            with_pages += bool(item.page_refs)
            expected = set().union(*(shown.get(key, set()) for key in RULE_ACCOUNTS[item.rule_code]))
            ok = bool(item.page_refs) and set(item.page_refs) <= expected
            matched += ok
            print(f"  {'OK ' if ok else 'BAD'} {item.rule_code:34s} P.{item.page_refs}  展示行页码 {sorted(expected)}")

    print()
    print(f"异常项 {total} 条：带页码 {with_pages}/{total}，页码与展示行一致 {matched}/{total}")
    print(f"ROE 可算出 {roe_ok}/{len(pdfs)} 份")
    return 0 if total == with_pages == matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
