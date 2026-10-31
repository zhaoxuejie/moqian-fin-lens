from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from dashboard.session import SessionData, filter_rows_by_statement
from export.guard import assert_clean
from export.markdown import DISCLAIMER


def render_xlsx(session: SessionData, path: str | Path) -> Path:
    filing = session.latest
    rows = filter_rows_by_statement(filing.rows)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    summary = workbook.active
    summary.title = "说明"
    summary.append(["公司", session.company_name])
    summary.append(["证券代码", session.stock_code or "—"])
    summary.append(["报告期", filing.period])
    summary.append(["页数", filing.pages])
    summary.append(["免责声明", DISCLAIMER])

    metrics_sheet = workbook.create_sheet("关键指标")
    metrics_sheet.append(["指标", "数值", "单位", "口径", "缺失原因"])
    for metric in filing.metrics:
        metrics_sheet.append(
            [
                metric.label,
                None if metric.value is None else float(metric.value),
                metric.unit,
                metric.formula,
                metric.missing_reason,
            ]
        )

    for kind, name in (("income", "利润表"), ("balance", "资产负债表"), ("cashflow", "现金流量表")):
        sheet = workbook.create_sheet(name)
        sheet.append(["科目", "本期", "上期", "页码"])
        for row in rows.get(kind, []):
            cells = {cell.period: cell.value for cell in row.cells}
            sheet.append(
                [
                    row.label,
                    None if cells.get("current") is None else float(cells["current"]),
                    None if cells.get("previous") is None else float(cells["previous"]),
                    row.page,
                ]
            )

    anomalies = workbook.create_sheet("异常项")
    anomalies.append(["规则", "标题", "说明"])
    for item in filing.anomalies:
        anomalies.append([item.rule_code, item.title, item.text])

    workbook.save(target)

    text_parts = [DISCLAIMER, session.company_name]
    for metric in filing.metrics:
        text_parts.append(metric.formula)
        if metric.missing_reason:
            text_parts.append(metric.missing_reason)
    for item in filing.anomalies:
        text_parts.extend([item.title, item.text])
    assert_clean("\n".join(text_parts))
    return target
