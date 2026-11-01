from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from dashboard.compare import build_comparison
from dashboard.session import SessionData, filter_rows_by_statement
from export.guard import assert_clean
from export.markdown import DISCLAIMER


def render_xlsx(session: SessionData, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    summary = workbook.active
    summary.title = "说明"
    summary.append(["公司", session.company_name])
    summary.append(["证券代码", session.stock_code or "—"])
    summary.append(["期间", "、".join(filing.period for filing in session.filings)])
    summary.append(["免责声明", DISCLAIMER])

    text_parts = [DISCLAIMER, session.company_name]
    periods = [filing.period for filing in session.filings]

    for filing in session.filings:
        rows = filter_rows_by_statement(filing.rows)
        summary.append([f"{filing.period} 页数", filing.pages])

        metrics_sheet = workbook.create_sheet(f"{filing.period} 指标")
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
            text_parts.append(metric.formula)
            if metric.missing_reason:
                text_parts.append(metric.missing_reason)

        for kind, name in (("balance", "资产负债表"), ("income", "利润表"), ("cashflow", "现金流量表")):
            sheet = workbook.create_sheet(f"{filing.period} {name}")
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

        anomalies = workbook.create_sheet(f"{filing.period} 异常")
        anomalies.append(["规则", "标题", "说明"])
        for item in filing.anomalies:
            anomalies.append([item.rule_code, item.title, item.text])
            text_parts.extend([item.title, item.text])

    if len(periods) > 1:
        comparison = build_comparison(session)
        sheet = workbook.create_sheet("跨年对比")
        header = ["科目"] + [f"{period} 值" for period in periods]
        header += [f"{period} 同比" for period in periods[1:]]
        sheet.append(header)
        for kind in ("balance", "income", "cashflow"):
            for row in comparison["statements"][kind]["rows"]:
                values = [None if value is None else float(value) for value in row["values"]]
                yoy = [None if item is None else round(item, 2) for item in row["yoy"][1:]]
                sheet.append([row["label"]] + values + yoy)

    workbook.save(target)

    assert_clean("\n".join(text_parts))
    return target
