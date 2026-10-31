"""生成科目对齐评估集（data/gold/align-100.json → tests/eval/gold/）。

构成（共 100 条）：
- 60 条真实报表标签：取自 10 份年报三表页，期望值由 Schema 精确别名确定（构造性通过，用于验证链路接线）；
- 25 条变体：覆盖「其中：」「减：」前缀、单位后缀、全角括号等归一化路径；
- 15 条负样本：表头、报表标题、分组标题等，期望「不对齐」。

用法：
    .venv\\Scripts\\python.exe tests/eval/build_align_gold.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from align import normalize_label  # noqa: E402
from parse import PdfDoc  # noqa: E402
from parse.labels import extract_labels  # noqa: E402
from schema import load_accounts  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"
OUT_FILE = OUT_DIR / "align-100.json"

STATEMENT_KINDS = ("income", "balance", "cashflow")
PER_REPORT = 6

VARIANTS: list[tuple[str, str, str]] = [
    ("其中：营业收入", "income", "revenue"),
    ("减：营业成本", "income", "cost_of_sales"),
    ("加：其他收益", "income", "other_income"),
    ("营业收入（元）", "income", "revenue"),
    ("营业总收入（人民币元）", "income", "revenue_total"),
    ("归属于母公司所有者的净利润", "income", "net_profit_attributable"),
    ("归属于母公司股东的净利润（元）", "income", "net_profit_attributable"),
    ("净利润（元）", "income", "net_profit"),
    ("营业利润（元）", "income", "operating_profit"),
    ("利润总额（元）", "income", "total_profit"),
    ("所得税费用（元）", "income", "income_tax"),
    ("研发费用", "income", "rd_expenses"),
    ("基本每股收益", "income", "basic_eps"),
    ("存货（元）", "balance", "inventory"),
    ("商誉（元）", "balance", "goodwill"),
    ("资产总计（元）", "balance", "total_assets"),
    ("负债合计（元）", "balance", "total_liabilities"),
    ("所有者权益合计（元）", "balance", "total_equity"),
    ("短期借款（元）", "balance", "short_term_borrowings"),
    ("应收账款（元）", "balance", "accounts_receivable"),
    ("应付账款（元）", "balance", "accounts_payable"),
    ("经营活动产生的现金流量净额（元）", "cashflow", "ocf_net"),
    ("销售商品、提供劳务收到的现金（元）", "cashflow", "cash_received_from_sales"),
    ("支付其他与经营活动有关的现金（元）", "cashflow", "other_cash_paid_operating"),
    ("期末现金及现金等价物余额（元）", "cashflow", "ending_cash"),
]

NEGATIVES: list[tuple[str, str]] = [
    ("合并资产负债表", "balance"),
    ("合并利润表", "income"),
    ("合并现金流量表", "cashflow"),
    ("单位：元", "income"),
    ("项目", "balance"),
    ("附注", "income"),
    ("法定代表人", "balance"),
    ("编制单位", "balance"),
    ("币种：人民币", "income"),
    ("流动资产：", "balance"),
    ("非流动资产：", "balance"),
    ("流动负债：", "balance"),
    ("经营活动产生的现金流量：", "cashflow"),
    ("筹资活动产生的现金流量：", "cashflow"),
    ("＃＠乱码科目", "income"),
]


def main() -> int:
    schema = load_accounts()
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    cases: list[dict[str, object]] = []

    for gold_file in sorted(GOLD_DIR.glob("*年度报告.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            continue
        picked = 0
        with PdfDoc(pdf) as doc:
            for kind in STATEMENT_KINDS:
                start = gold["statements"][kind]["start"]
                for page in range(start, start + 2):
                    if page > doc.page_count or picked >= PER_REPORT:
                        continue
                    for label in extract_labels(doc.page_text(page)):
                        account = schema.resolve(normalize_label(label))
                        if account is None or account.statement != kind:
                            continue
                        cases.append(
                            {
                                "raw": label,
                                "statement": kind,
                                "expected": account.code,
                                "source": "auto",
                                "report": gold_file.stem,
                                "page": page,
                            }
                        )
                        picked += 1
                        if picked >= PER_REPORT:
                            break

    for raw, statement, expected in VARIANTS:
        cases.append(
            {"raw": raw, "statement": statement, "expected": expected, "source": "variant"}
        )
    for raw, statement in NEGATIVES:
        cases.append(
            {"raw": raw, "statement": statement, "expected": None, "source": "negative"}
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for case in cases:
        counts[str(case["source"])] = counts.get(str(case["source"]), 0) + 1
    print(f"共 {len(cases)} 条：{counts}，写入 {OUT_FILE}")
    return 0 if len(cases) == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
