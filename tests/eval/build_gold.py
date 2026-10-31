"""生成评估集金标（data/gold → 由调用方复制到 tests/eval/gold/）。

金标来源优先级（越靠前越独立于 parse/locate.py 的启发式）：
1. PDF 书签（bookmark）：年报自带目录书签，页码由发行方提供，独立可信；
2. 编号标题规则（numbered）：标题形如「3、合并利润表」且带单位行；
3. 启发式兜底（heuristic-weak）：前两者都不可用时，标记为弱金标，需人工复核。

用法：
    .venv\\Scripts\\python.exe tests/eval/build_gold.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parse import PdfDoc, compress_whitespace, detect_start_pages  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent / "pdf"
# 先写到 data/gold（本机可写），再由调用方复制到 tests/eval/gold/
GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"

KINDS = ("income", "balance", "cashflow")
BOOKMARK_PREFIX = {
    "income": "合并利润表",
    "balance": "合并资产负债表",
    "cashflow": "合并现金流量表",
}
NUMBERED_HEADING = re.compile(r"(?:^|[^0-9])(\d{1,2})、合并(资产负债表|利润表|现金流量表)")
KIND_BY_NAME = {"资产负债表": "balance", "利润表": "income", "现金流量表": "cashflow"}
UNIT_MARKERS = ("单位：元", "单位:元", "单位：人民币元", "单位：千元", "单位：万元")


def from_bookmarks(bookmarks: list[tuple[str, int]]) -> dict[str, int | None]:
    found: dict[str, int | None] = dict.fromkeys(KINDS)
    for title, page in bookmarks:
        if "母公司" in title:
            continue
        for kind, prefix in BOOKMARK_PREFIX.items():
            if found[kind] is None and prefix in title:
                found[kind] = page
    return found


def from_numbered_heading(pages: list[str]) -> dict[str, int | None]:
    found: dict[str, int | None] = dict.fromkeys(KINDS)
    for index, text in enumerate(pages, start=1):
        flat = compress_whitespace(text)
        if not any(marker in flat for marker in UNIT_MARKERS):
            continue
        for match in NUMBERED_HEADING.finditer(flat):
            kind = KIND_BY_NAME[match.group(2)]
            if found[kind] is None:
                found[kind] = index
    return found


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for pdf in sorted(PDF_DIR.glob("*/*.pdf")):
        with PdfDoc(pdf) as doc:
            pages = [doc.page_text(i) for i in range(1, doc.page_count + 1)]
            page_count = doc.page_count
            bookmarks = doc.bookmarks()

        by_bookmark = from_bookmarks(bookmarks)
        by_numbered = from_numbered_heading(pages)
        heuristic = detect_start_pages(pages)

        statements: dict[str, dict[str, object]] = {}
        for kind in KINDS:
            if by_bookmark[kind] is not None:
                start, source = by_bookmark[kind], "bookmark"
            elif by_numbered[kind] is not None:
                start, source = by_numbered[kind], "numbered"
            else:
                start, source = heuristic[kind], "heuristic-weak"
            evidence = ""
            if start:
                evidence = " ".join(pages[start - 1].split())[:120]
            statements[kind] = {"start": start, "source": source, "evidence": evidence}

        disagreed = {
            kind: {"gold": statements[kind]["start"], "heuristic": heuristic[kind]}
            for kind in KINDS
            if statements[kind]["start"] != heuristic[kind]
        }

        gold = {
            "code": pdf.stem.split("_")[0],
            "company": pdf.stem.split("_")[1],
            "period": pdf.stem.split("_")[2].split("年")[0],
            "pages": page_count,
            "statements": statements,
            "heuristic_disagreement": disagreed,
        }
        (GOLD_DIR / f"{pdf.stem}.json").write_text(
            json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rows.append((pdf.stem, statements, disagreed))

    print(f"{'file':<44} {'income':>16} {'balance':>16} {'cashflow':>16}")
    for stem, statements, disagreed in rows:
        cells = [
            f"{statements[k]['start']}({statements[k]['source']})" for k in KINDS
        ]
        flag = "  DIFF" if disagreed else ""
        print(f"{stem:<44} {cells[0]:>16} {cells[1]:>16} {cells[2]:>16}{flag}")
        if disagreed:
            print("   ", disagreed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
