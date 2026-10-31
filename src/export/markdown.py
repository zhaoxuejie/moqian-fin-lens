from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dashboard.session import SessionData, filter_rows_by_statement
from export.guard import assert_clean

DISCLAIMER = (
    "本工具仅对用户上传的财报文档做信息提取与整理，所呈现内容均来自原文并标注页码，"
    "不构成任何投资建议。数据请以公司在指定媒体披露的正式报告为准，使用前请自行核验。"
)


def _fmt(value) -> str:
    return "未披露" if value is None else str(value)


def _cell(value) -> str:
    return str(value).replace("|", "\\|")


def render_markdown(session: SessionData) -> str:
    filing = session.latest
    rows = filter_rows_by_statement(filing.rows)
    lines: list[str] = []

    lines.append(f"# {session.company_name} {filing.period} 年年度报告 财务视图")
    lines.append("")
    lines.append(f"- 证券代码：{session.stock_code or '—'}")
    lines.append(f"- 报告期：{filing.period} 年")
    lines.append(f"- 页数：{filing.pages}")
    lines.append(f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("> **免责声明**：" + DISCLAIMER)
    lines.append("")

    lines.append("## 一、关键指标")
    lines.append("")
    lines.append("| 指标 | 数值 | 单位 | 口径 |")
    lines.append("| ---- | ---- | ---- | ---- |")
    for metric in filing.metrics:
        value = "原文未披露" if metric.value is None else f"{metric.value}"
        lines.append(
            f"| {_cell(metric.label)} | {_cell(value)} | {_cell(metric.unit)} | {_cell(metric.formula)} |"
        )
    lines.append("")

    statement_names = {"income": "利润表", "balance": "资产负债表", "cashflow": "现金流量表"}
    lines.append("## 二、三大报表")
    lines.append("")
    for kind, name in statement_names.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| 科目 | 本期 | 上期 | 页码 |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for row in rows.get(kind, []):
            cells = {cell.period: cell.raw for cell in row.cells}
            lines.append(
                f"| {_cell(row.label)} | {_cell(_fmt(cells.get('current')))} | "
                f"{_cell(_fmt(cells.get('previous')))} | P.{row.page} |"
            )
        lines.append("")

    lines.append("## 三、异常项")
    lines.append("")
    if filing.anomalies:
        for item in filing.anomalies:
            lines.append(f"- **{item.title}**：{item.text}")
    else:
        lines.append("- 本期未触发异常规则。")
    lines.append("")

    lines.append("## 四、说明")
    lines.append("")
    lines.append("所有数字来自原文并标注页码；缺失项以「未披露」标注，不做推测。")
    lines.append("")

    text = "\n".join(lines)
    # 只校验「生成文案」：原文科目名（如「买入返售金融资产」）不参与禁用词判定
    generated = [DISCLAIMER, "所有数字来自原文并标注页码；缺失项以「未披露」标注，不做推测。"]
    generated.extend(metric.formula for metric in filing.metrics)
    for item in filing.anomalies:
        generated.extend([item.title, item.text])
    assert_clean("\n".join(generated))
    return text


def write_markdown(session: SessionData, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(session), encoding="utf-8")
    return target
