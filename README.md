# finance-agent

上传 A 股财报 PDF，把两三百页、表格跨页的报表整理成**可核对**的财务视图：三表结构化、20 项关键指标、11 组图表、异常项提示，每个数字都能回到原文页码。

## 版本信息

当前版本：v0.3.0（内测）
项目阶段：v0.3.0 内测版已发布（TASK-001～020 全部完成）

## 概述

- 解决什么问题：年报动辄两三百页、表格跨页、科目写法五花八门，看懂成本高，且不敢信自动抽取的数字。
- 核心能力（v1.0 目标）：上传 → 解析 → 科目对齐 → 指标计算 → 11 组图表 → 溯源核对 → 导出。
- 适用场景：价投散户快速看财报质量、财经创作者取干净表格与素材、学生理解三表勾稽。
- 明确不做：涨跌预测、估值打分、荐股、自动抓取财报、交易、港股 / 美股、扫描件 OCR（v1.1 评估）。
- 交付形态：网页版，浏览器打开即用；v1.0 无账号体系。

## 快速启动

> 前置依赖：Python 3.11+

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows；macOS / Linux 用 source .venv/bin/activate
pip install -e ".[dev]"       # 国内网络可加 -i https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env          # Windows PowerShell：Copy-Item .env.example .env
uvicorn app.main:app --reload # 打开 http://127.0.0.1:8000
```

验证与测试：

```bash
curl http://127.0.0.1:8000/healthz   # {"status":"ok"}
pytest --cov                          # 覆盖率门槛 80%
```

容器方式（需 Docker 守护进程运行）：

```bash
docker compose up --build
docker compose exec app curl -s http://127.0.0.1:8000/healthz
```

## 部署与可观测

- 健康检查：`GET /healthz` 返回 `{"status":"ok"}` 并验证数据库可读；数据库异常时返回 503。
- 运行摘要：每次解析追加一行 JSON 到 `data/logs/runs.jsonl`（页数、耗时、勾稽结论、失败原因），超过 5MB 自动轮转。
- 告警口径：累计 10 次解析后，成功率低于 90% 会打印 `parse_success_rate_low` 警告日志。
- 发布：`bash scripts/release.sh 1.0.0 --dry-run` 预览；去掉 `--dry-run` 会更新 CHANGELOG、提交并打 tag（不 push）。

## 目录概览

```text
finance-agent/
├── src/
│   ├── app/             # FastAPI 入口、模板、静态资源
│   ├── core/            # 配置、日志、错误码、响应体
│   ├── store/           # SQLite 访问层与迁移
│   └── parse|schema|align|metrics|anomaly|dashboard|trace|export|jobs|ops/
├── docs/                # readme、prd、architecture、api-contract、tasks、archive
├── scripts/             # 发布等辅助脚本
├── tests/               # unit、integration、eval（评测集与金标）
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/   # CI：Markdown、shell、pytest
```

## 开发流程

1. 文档先行：`docs/prd.md` → `docs/architecture.md`（含 ADR）→ `docs/api-contract.md`，逐份人工确认。
2. 任务卡：`docs/tasks/` 一任务一文件，按批次增量拆解，确认后更新 `docs/tasks/readme.md` 索引。
3. 开发：只开发「前置依赖全部 done」的任务，验收与评测通过才标记 done。

## 规范

- 贡献规范：见 `CONTRIBUTING.md`
- AI 开发约束：见 `AGENTS.md`
- 版本变更记录：见 `CHANGELOG.md`
- 任务索引：见 `docs/tasks/readme.md`
