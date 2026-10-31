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
