# tests/eval

评测集目录。对应 `docs/prd.md` 附录 A 与 `docs/tasks/task-002-parser-and-statement-locating.md`。

## 目录约定

```text
tests/eval/
├── pdf/                  # 10 份真实财报 PDF（不提交到 git，见 .gitignore）
├── gold/                 # 金标 JSON，随代码入库
└── failures/             # 失败样本留档，进入回归集
```

## 金标格式（gold/<company>-<period>.json）

```json
{
  "company": "示例精密制造股份有限公司",
  "period": "2023",
  "report_type": "annual",
  "pages": 286,
  "statements": {
    "income": { "start": 42, "end": 45 },
    "balance": { "start": 76, "end": 79 },
    "cashflow": { "start": 103, "end": 106 }
  },
  "numbers": [
    { "account_code": "revenue_total", "page": 42, "raw": "12,180,436,512.33", "value": 12180436512.33 }
  ]
}
```

## 说明

- PDF 原件体积大且涉及版权，不入库；本地按需下载后放入 `pdf/`。
- 金标由人工标注，改动需在 PR 中说明来源与理由。

## 交叉核对断言（TASK-024）

金标也是脚本生成的，产品和金标出同一种错时，金标评测照样通过。`run_crosscheck_eval.py` 不看金标，拿年报自己的另一处披露核对产品输出：

- 断言 A：报表取到的营业收入（本期、上期）与第二节「主要会计数据」一节的营业收入按分一致。单位取科目名后的「（元）」「（千元）」或该页「单位：」行；声明追溯调整的年报，上期取「调整后」那一列。读不到这一节时记「未核对」，不算通过。
- 断言 B：指标标为「原文未披露：X」时，三张报表的页范围里没有科目 X 的金额行。科目名后面只有「-」的记「列示为空」，单独列出，不算违反。

行读取和金额换算都在脚本里独立实现，不复用产品的表格还原、单位识别和科目匹配。输出存档在 `reports/crosscheck.txt`。
