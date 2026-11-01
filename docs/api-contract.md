# 财报透视（finance-agent）接口契约
当前版本：v0.1.0（草案）
关联 PRD：`docs/prd.md` v0.2.0（confirmed）
关联架构：`docs/architecture.md` v0.1.0
文档状态：draft，待评审
撰写日期：2026-10-31

> 约定：
> - 状态：draft / stable / deprecated；deprecated 接口必须写迁移指引
> - v1.0 所有接口前缀 `/api/v1`，不兼容变更走新前缀，旧前缀标 deprecated
> - 本文件只定义契约，不定义实现与存储细节

## 通用约定

### 基础信息

- 基础地址：`https://<host>`（本地开发 `http://127.0.0.1:8000`）
- 接口前缀：`/api/v1`
- 编码：请求与响应均为 UTF-8
- 时间格式：ISO 8601，带时区偏移，如 `2026-10-31T17:41:53+08:00`
- 报告期格式：年报 `2023`，半年报 `2023H1`

### 统一请求头

| 请求头 | 必填 | 说明 |
| ---- | ---- | ---- |
| `Content-Type` | 上传接口必填 | `multipart/form-data` 或 `application/json` |
| `X-Request-Id` | 否 | 客户端生成的追踪号；不传则服务端生成 |
| `X-Client` | 否 | 客户端标识，用于区分网页与脚本调用 |

### 统一返回格式

```json
{
  "code": 0,
  "msg": "ok",
  "data": {},
  "request_id": "req_7f3a2c9e"
}
```

- `code = 0` 表示成功；非 0 为业务错误码，与 HTTP 状态码同时给出。
- `data` 在错误响应中为 `null`。
- `request_id` 始终返回，便于排查。

### 鉴权与匿名会话

v1.0 无账号体系，采用**匿名会话 Cookie**：

- 首次访问任意页面时，服务端下发 `fa_sid`（httpOnly、SameSite=Lax、30 天）。
- 会话与 Cookie 绑定，`session_id` 同时出现在 URL 中，但服务端必须校验 Cookie 归属，禁止仅凭 URL 访问。
- Cookie 丢失即无法找回该会话（不提供找回入口），页面需明确提示。
- 不采集手机号、邮箱、姓名等身份信息。

### 限流

| 维度 | 限制 | 超限返回 |
| ---- | ---- | ---- |
| 单 IP 上传 | 10 次 / 小时 | `429` + `Retry-After` |
| 单 IP API | 120 次 / 分钟 | `429` + `Retry-After` |
| 并发解析任务 | 5 个（全局） | 任务进入排队，状态 `queued` |

### 上传约束

| 项 | 约束 | 违反时错误码 |
| ---- | ---- | ---- |
| 类型 | 仅 PDF（同时校验扩展名与文件头 `%PDF`） | `40001` |
| 大小 | ≤ 50MB | `40002` |
| 页数 | ≤ 400 页 | `40003` |
| 单会话期数 | ≤ 5 期 | `40005` |
| 公司一致性 | 同一会话内公司名必须一致 | `40004` |

### 错误码规范

| code | HTTP | 含义 | 客户端处理 |
| ---- | ---- | ---- | ---- |
| 0 | 200 | 成功 | — |
| 40001 | 400 | 文件类型不合法 | 提示仅支持 PDF |
| 40002 | 400 | 文件超过 50MB | 提示压缩或拆分 |
| 40003 | 400 | 页数超过 400 页 | 提示仅支持主体报告 |
| 40004 | 400 | 与会话内公司不一致 | 提示换新会话上传 |
| 40005 | 400 | 会话期数已满（5 期） | 提示新建会话 |
| 40006 | 400 | 请求参数缺失或类型错误 | 提示检查入参 |
| 40301 | 403 | 会话归属校验失败 | 提示 Cookie 丢失，重新上传 |
| 40401 | 404 | 会话不存在 | 返回首页 |
| 40402 | 404 | 任务或财报不存在 | 提示刷新 |
| 40901 | 409 | 期次尚未解析完成 | 轮询任务状态 |
| 42201 | 422 | 解析失败（版式/文件损坏） | 展示错误详情与重试入口 |
| 42202 | 422 | 三表定位失败 | 展示失败页码，建议人工核对 |
| 42901 | 429 | 触发限流 | 按 `Retry-After` 重试 |
| 50001 | 500 | 服务内部错误 | 展示 request_id |
| 50301 | 503 | 解析队列已满 | 提示稍后重试 |

## 页面路由

页面返回 HTML，交互由页面内 JS 调 JSON 接口完成。

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| GET | `/` | 首页：上传区 + 使用说明 + 免责声明 |
| GET | `/s/{session_id}` | 看板页：基础信息、指标卡、三表、11 组图表、异常项、导出入口 |
| GET | `/s/{session_id}?tab=statements` | 直接定位到三表 Tab（其余 tab：`charts`、`anomaly`） |
| GET | `/s/{session_id}/export/{export_id}` | 下载已生成的导出文件（下载即失效策略见 4.8） |

页面内联数据：看板页首屏由服务端直接渲染基础信息与指标卡，避免白屏；图表数据由 `GET /api/v1/sessions/{id}/charts` 异步补。

## 接口列表

### 接口 1：上传财报

路径：`POST /api/v1/uploads`
状态：stable
版本：v1
内容类型：`multipart/form-data`

请求参数：

| 参数名 | 类型 | 是否必填 | 说明 |
| ---- | ---- | ---- | ---- |
| file | file | 是 | PDF 文件，≤ 50MB |
| session_id | string | 否 | 已有会话 ID；不传则新建会话 |
| report_type | string | 否 | `annual` / `semi`；不传则从正文识别 |

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "session_id": "s_9f2c1a",
    "filing": {
      "filing_id": "f_01",
      "report_type": "annual",
      "period": "2023",
      "status": "queued"
    },
    "job": { "job_id": "j_1001", "state": "queued", "queue_position": 1 }
  },
  "request_id": "req_7f3a2c9e"
}
```

说明：上传成功即返回 `202`；解析在后台进行，客户端轮询任务接口。

### 接口 2：查询任务状态

路径：`GET /api/v1/jobs/{job_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "job_id": "j_1001",
    "state": "parsing",
    "progress": 0.42,
    "stage": "table_extract",
    "queue_position": 0,
    "error": null,
    "started_at": "2026-10-31T17:42:10+08:00"
  },
  "request_id": "req_8a1b"
}
```

`state` 枚举：`queued` / `parsing` / `aligning` / `computing` / `done` / `failed` / `interrupted`。
`error` 为 `{code, msg, detail:{page, stage}}`，失败时给出页码与阶段。

### 接口 3：会话详情

路径：`GET /api/v1/sessions/{session_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "session_id": "s_9f2c1a",
    "company_name": "示例精密制造股份有限公司",
    "stock_code": "300000.SZ",
    "filing_count": 3,
    "filings": [
      {
        "filing_id": "f_01",
        "report_type": "annual",
        "period": "2023",
        "status": "done",
        "audit_opinion": "标准无保留意见",
        "pages": 286,
        "parsed_at": "2026-10-31T17:43:02+08:00"
      }
    ],
    "checks": [
      { "rule": "balance_sheet_identity", "passed": true, "diff": 0 }
    ],
    "unaligned_count": 2,
    "created_at": "2026-10-31T17:41:00+08:00"
  },
  "request_id": "req_9c2d"
}
```

### 接口 4：三表数据

路径：`GET /api/v1/sessions/{session_id}/statements?filing_id={filing_id}`
状态：stable
版本：v1

请求参数：

| 参数名 | 类型 | 是否必填 | 说明 |
| ---- | ---- | ---- | ---- |
| filing_id | string | 否 | 不传则取会话内最新一期 |
| kind | string | 否 | `income` / `balance` / `cashflow`；不传返回三张 |

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "filing_id": "f_01",
    "period": "2023",
    "statements": [
      {
        "kind": "income",
        "unit": "元",
        "rows": [
          {
            "account_code": "revenue_total",
            "label": "营业总收入",
            "value": 12180436512.33,
            "page": 42,
            "snippet": "营业总收入 12,180,436,512.33 元；其中：主营业务收入 11,902,118,770.15 元",
            "confidence": 0.98,
            "source": "rule"
          },
          {
            "account_code": "cost_of_sales",
            "label": "营业成本",
            "value": null,
            "missing_reason": "原文未披露",
            "page": null,
            "snippet": null
          }
        ]
      }
    ]
  },
  "request_id": "req_a1f2"
}
```

约定：

- `value` 一律为标准单位（元），显示层负责换算成亿元。
- `value = null` 时必须带 `missing_reason`，且不得在图表中显示为 0。
- 每个非空行必须带 `page` 与 `snippet`（对应 PRD T3：无出处不展示）。

### 接口 5：指标列表

路径：`GET /api/v1/sessions/{session_id}/metrics?filing_id={filing_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "filing_id": "f_01",
    "metrics": [
      {
        "code": "gross_margin",
        "label": "毛利率",
        "value": 22.3,
        "unit": "%",
        "yoy": -3.8,
        "yoy_unit": "pct",
        "formula": "(营业总收入 - 营业成本) / 营业总收入",
        "missing_reason": null,
        "trace": { "entry_id": "e_1001", "page": 42 }
      }
    ]
  },
  "request_id": "req_b2c3"
}
```

`unit` 枚举：`元` / `%` / `pct` / `倍` / `天` / `次`。
`yoy_unit` 为 `%`（相对增速）或 `pct`（绝对变动百分点）。

### 接口 6：图表数据

路径：`GET /api/v1/sessions/{session_id}/charts?filing_id={filing_id}`
状态：stable
版本：v1

响应示例（截取 c2、c7）：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "charts": [
      {
        "id": "c2",
        "group": "盈利与增长",
        "title": "扣非净利润与增速",
        "x": ["2023", "2024", "2025"],
        "series": [
          { "name": "扣非净利润", "type": "bar", "unit": "元", "yAxisIndex": 0, "sign_colors": true, "data": [810264881.3, 1240000000, 988000000] },
          { "name": "扣非增速", "type": "line", "unit": "%", "yAxisIndex": 1, "data": [-12.5, 53.0, -20.3] }
        ],
        "meta": {
          "caliber": "扣非净利润取合并利润表；扣非增速按报告上期比较列计算",
          "sources": [{ "label": "P.42", "page": 42 }],
          "missing": []
        }
      },
      {
        "id": "c7",
        "group": "现金质量",
        "title": "经营现金流与自由现金流",
        "x": ["2023", "2024", "2025"],
        "series": [
          { "name": "经营现金流", "type": "bar", "unit": "元", "yAxisIndex": 0, "sign_colors": true, "data": [490258731.44, 1100000000, -320000000] },
          { "name": "自由现金流", "type": "bar", "unit": "元", "yAxisIndex": 0, "sign_colors": true, "data": [121000000, 510000000, -910000000] },
          { "name": "现金含量", "type": "line", "unit": "倍", "yAxisIndex": 1, "markLine": { "value": 1.0, "label": "1.0 警戒" }, "data": [0.57, 1.04, -0.41] }
        ],
        "meta": { "caliber": "自由现金流 = 经营现金流 − 购建长期资产支付的现金", "sources": [], "missing": [] }
      }
    ]
  },
  "request_id": "req_c3d4"
}
```

约定：

- `id` 固定为 `c1`～`c11`，`group` 为 `盈利与增长` / `现金质量` / `风险与结构`，顺序即页面顺序；异常项走独立接口（卡片形态）。
- `series[].unit` 必填，枚举 `元` / `%` / `倍` / `次`；同一图内不同单位必须以 `yAxisIndex` 分轴，不得共用一根轴。
- `sign_colors: true` 的柱状系列按数值正负着色（正值品牌红、负值绿色）。
- `series[].markLine` 用于参考线（ROE 15%、资产负债率 60%、现金含量 1.0），`value` 为参考值，`label` 为展示文案。
- `missing` 非空时列出具体系列名，对应图表在页面显示「数据不足」占位，不允许补 0。
- 多期会话 `x` 为会话内各期年份；单期会话用报告上期比较列补成两点，首点标签为 `<年份>（比较列）`，依赖平均余额的系列首点为 `null`。

### 接口 7：异常项

路径：`GET /api/v1/sessions/{session_id}/anomalies`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "items": [
      {
        "rule_code": "ar_growth_exceeds_revenue",
        "title": "应收账款增速连续两年高于营收增速",
        "text": "2023 年应收增长 41.5%，营收增长 17.6%。",
        "evidence": [
          { "account_code": "accounts_receivable", "value": 3170442901.35, "period": "2023" },
          { "account_code": "revenue_total", "value": 12180436512.33, "period": "2023" }
        ],
        "page_refs": [87, 42]
      }
    ]
  },
  "request_id": "req_d4e5"
}
```

约定：`text` 由模板生成，禁止自由文本；`page_refs` 至少一个，否则不返回该项。

### 接口 8：溯源详情

路径：`GET /api/v1/sessions/{session_id}/trace/{entry_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "entry_id": "e_1001",
    "account_code": "revenue_total",
    "label": "营业总收入",
    "page": 42,
    "snippet": "营业总收入 12,180,436,512.33 元；其中：主营业务收入 11,902,118,770.15 元，其他业务收入 278,317,742.18 元。",
    "unit_note": "单位换算：元 → 亿元，保留两位小数",
    "formula": null,
    "bbox": { "x0": 112.4, "y0": 386.2, "x1": 444.8, "y1": 401.5 }
  },
  "request_id": "req_e5f6"
}
```

约定：`bbox` 为 v1.1 坐标跳转预留字段，v1.0 前端不消费；`unit_note` 与 `formula` 至少一个非空。

### 接口 9：创建导出

路径：`POST /api/v1/sessions/{session_id}/exports`
状态：stable
版本：v1

请求参数：

| 参数名 | 类型 | 是否必填 | 说明 |
| ---- | ---- | ---- | ---- |
| kind | string | 是 | `markdown` / `xlsx` |
| filing_ids | string[] | 否 | 不传则导出整会话 |

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "export_id": "x_01",
    "state": "generating",
    "download_url": null
  },
  "request_id": "req_f6a7"
}
```

### 接口 10：查询导出

路径：`GET /api/v1/exports/{export_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "export_id": "x_01",
    "state": "ready",
    "download_url": "/s/s_9f2c1a/export/x_01",
    "expires_at": "2026-10-31T18:41:00+08:00"
  },
  "request_id": "req_g7b8"
}
```

约定：导出文件保留 1 小时，过期后 `download_url` 无效；`state` 枚举 `generating` / `ready` / `failed`。

### 接口 11：清空会话

路径：`DELETE /api/v1/sessions/{session_id}`
状态：stable
版本：v1

响应示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": { "deleted": true },
  "request_id": "req_h8c9"
}
```

约定：级联删除该会话的期次、结构化数据、溯源片段、导出文件与任务记录；不可恢复。

## 数据对象

| 对象 | 字段 | 说明 |
| ---- | ---- | ---- |
| Session | `session_id`、`company_name`、`stock_code`、`filing_count`、`created_at` | 一次上传会话 |
| Filing | `filing_id`、`report_type`、`period`、`status`、`audit_opinion`、`pages`、`parsed_at` | 单期财报 |
| StatementRow | `account_code`、`label`、`value`、`unit`、`page`、`snippet`、`confidence`、`source`、`missing_reason` | 三表行；`source` 枚举 `rule` / `fuzzy` / `llm` / `manual` |
| Metric | `code`、`label`、`value`、`unit`、`yoy`、`yoy_unit`、`formula`、`missing_reason`、`trace` | 20 项指标 |
| ChartPayload | `id`、`title`、`kind`、`unit`、`x`、`series`、`meta` | 图表数据；`kind` 枚举 `combo` / `grouped-bar` / `mini-multiples` |
| AnomalyItem | `rule_code`、`title`、`text`、`evidence`、`page_refs` | 异常项，文案模板生成 |
| TraceDetail | `entry_id`、`page`、`snippet`、`unit_note`、`formula`、`bbox` | 溯源详情 |
| Job | `job_id`、`state`、`progress`、`stage`、`queue_position`、`error` | 解析任务 |

数值约定：

- 金额统一为「元」，浮点保留两位小数；显示层换算亿元。
- 百分比保留两位小数，`pct` 表示百分点变动。
- `null` 只用于「原文未披露」，必须同时给 `missing_reason`。

## 内部模块契约（供任务卡引用）

| 模块 | 契约 | 返回 |
| ---- | ---- | ---- |
| `parse.open_pdf(path)` | 打开 PDF，返回页数与逐页文本访问器 | `PdfDoc` |
| `parse.locate_statements(doc)` | 定位三表页范围 | `{income:(s,e), balance:(s,e), cashflow:(s,e)}` |
| `parse.extract_table(doc, page_range)` | 还原表格，带坐标 | `list[TableRow]` |
| `parse.normalize(value_text, unit_hint)` | 数值归一 | `{value, unit, sign, is_missing}` |
| `align.map_account(row, schema, aliases)` | 科目映射 | `{account_code, confidence, source}` |
| `align.align_periods(filings)` | 多期对齐 | `list[AlignedSeries]` |
| `metrics.compute(filing, series)` | 计算 20 项指标 | `list[Metric]` |
| `metrics.check_balance(statements)` | 三表勾稽 | `CheckResult` |
| `anomaly.detect(series, metrics)` | 命中异常 | `list[AnomalyItem]` |
| `dashboard.charts.build_chart_set(filings)` | 装配 11 组图表 | `list[ChartPayload]` |
| `export.render_markdown(session)` | 渲染 md | `bytes` |
| `export.render_xlsx(session)` | 渲染 xlsx | `bytes` |

约定：模块间只通过上述数据对象传递，禁止跨模块直接读数据库。

## 接口变更记录

| 接口 | 变更内容 | 版本 | 关联ADR |
| ---- | ---- | ---- | ---- |
| — | 初版契约 | v0.1.0 | ADR-001 ～ ADR-007 |
| 接口 6 图表数据 | id 由 `v1`～`v7` 改为 `c1`～`c10`；新增 `group`、`series.unit`、`sign_colors`；单期会话横轴改为「比较列 + 当期」两点 | v0.3.1 | — |
| 接口 6 图表数据 | 新增 `c1`「营业总收入与增速」，其余图表 id 顺延为 `c2`～`c11` | v0.3.1 | ADR-009 |

## 废弃与迁移指引

| 接口 | 废弃版本 | 替代方案 | 迁移步骤 |
| ---- | ---- | ---- | ---- |
| 暂无 | - | - | - |

## 评审记录

| 评审人 | 时间 | 结论 | 备注 |
| ---- | ---- | ---- | ---- |
| 待填写 | - | - | 请重点确认：匿名会话 Cookie 方案、导出异步化、金额统一用「元」三条 |
