from __future__ import annotations

import re

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from anomaly.rules import AnomalyItem, detect
from metrics import MetricResult, check_statements, compute_metrics, pages_from_rows, values_from_rows
from parse import PdfDoc, locate_statements
from parse.normalize import normalize
from parse.table import CellValue, StatementRow, extract_statement_rows


@dataclass
class FilingData:
    filing_id: str
    period: str
    pages: int
    rows: dict[str, list[StatementRow]]
    values: dict[str, dict[str, dict]]
    metrics: list[MetricResult]
    checks: list
    anomalies: list[AnomalyItem]
    company_info: dict = field(default_factory=dict)
    page_texts: dict[int, str] = field(default_factory=dict)
    parsed_at: str = ""

    @property
    def metrics_by_code(self) -> dict[str, MetricResult]:
        return {item.code: item for item in self.metrics}


@dataclass
class SessionData:
    session_id: str
    company_name: str
    stock_code: str
    filings: list[FilingData] = field(default_factory=list)
    created_at: str = ""

    @property
    def latest(self) -> FilingData:
        return self.filings[-1]

    @property
    def periods(self) -> list[str]:
        return [filing.period for filing in self.filings]


STATEMENT_ANCHORS = {
    "income": ("营业总收入", "营业收入", "营业总成本"),
    "balance": ("货币资金", "流动资产", "资产总计"),
    "cashflow": ("销售商品", "经营活动产生的现金流量", "经营活动现金流入"),
}


PARENT_CUT_PATTERNS = {
    "income": ("营业总收入", "营业收入"),
    "balance": ("货币资金",),
    "cashflow": ("销售商品",),
}
STATEMENT_TERMINALS = {
    "balance": (
        "负债和所有者权益总计",
        "负债和所有者权益（或股东权益）总计",
        "负债和所有者权益合计",
        "负债和所有者权益（或股东权益）合计",
    ),
    "income": ("稀释每股收益",),
    "cashflow": ("期末现金及现金等价物余额",),
}


def _cut_parent_statement(rows: list[StatementRow], kind: str) -> list[StatementRow]:
    """合并报表之后若接着母公司报表，截断到合并报表的末行（含）。"""
    terminals = STATEMENT_TERMINALS.get(kind, ())
    for index, row in enumerate(rows):
        label = row.label.strip()
        if any(terminal in label for terminal in terminals):
            return rows[:index + 1]

    patterns = PARENT_CUT_PATTERNS.get(kind, ())
    seen = 0
    for index, row in enumerate(rows):
        label = row.label.strip()
        if not label:
            continue
        starts = (
            label.startswith(("一、", "1、"))
            or label.startswith(kind)
            or any(label.startswith(pattern) for pattern in patterns)
        )
        if any(pattern in label for pattern in patterns) and starts:
            seen += 1
            if seen == 2:
                return rows[:index]
    return rows


def _trim_to_statement(rows: list[StatementRow], kind: str) -> list[StatementRow]:
    anchors = STATEMENT_ANCHORS.get(kind, ())
    for index, row in enumerate(rows):
        if any(anchor in row.label for anchor in anchors):
            return _cut_parent_statement(rows[index:], kind)
    return rows


def filter_rows_by_statement(rows_by_kind: dict[str, list[StatementRow]]) -> dict[str, list[StatementRow]]:
    """按科目归属过滤行：利润表页里的母公司资产负债表尾行不进入利润表。"""
    from align import normalize_label
    from schema import load_accounts

    schema = load_accounts()
    filtered: dict[str, list[StatementRow]] = {}
    for kind, rows in rows_by_kind.items():
        kept: list[StatementRow] = []
        for row in _trim_to_statement(rows, kind):
            account = schema.resolve(normalize_label(row.label))
            if account is not None and account.statement != kind:
                continue
            if not row.cells and row.label.endswith("："):
                continue
            kept.append(row)
        filtered[kind] = kept
    return filtered


DEDUCTED_LABEL = "扣除非经常性损益"
DEDUCTED_AMOUNT = re.compile(r"\(?-?[\d,]+\.\d{2}\)?")


def _add_deducted_fallback(rows: dict[str, list[StatementRow]], pages: list[str]) -> dict[str, list[StatementRow]]:
    """扣非净利润通常披露在「主要财务指标」而非三表页，缺省时全文兜底抓取一次。"""
    if any("扣除非经常性损益" in row.label for row in rows.get("income", [])):
        return rows
    for index, text in enumerate(pages, start=1):
        flat = re.sub(r"\s+", "", text)
        position = flat.find(DEDUCTED_LABEL)
        if position == -1:
            continue
        window = flat[position:position + 160]
        label_end = window.find("净利润")
        if label_end == -1:
            continue
        tail = window[label_end + len("净利润"):]
        amounts = DEDUCTED_AMOUNT.findall(tail)
        if len(amounts) < 2:
            continue
        try:
            current = normalize(amounts[0]).value
            previous = normalize(amounts[1]).value
        except Exception:
            continue
        if current is None:
            continue
        cells = [CellValue(amounts[0], current, "current", index, (0.0, 0.0, 0.0, 0.0))]
        if previous is not None:
            cells.append(CellValue(amounts[1], previous, "previous", index, (0.0, 0.0, 0.0, 0.0)))
        rows.setdefault("income", []).append(
            StatementRow(
                label="归属于上市公司股东的扣除非经常性损益的净利润",
                page=index,
                snippet=window[:200],
                cells=tuple(cells),
                is_missing=False,
            )
        )
        return rows
    return rows


INFO_LABELS = {
    "公司的中文名称": "全称",
    "公司中文名称": "全称",
    "中文名称": "全称",
    "公司的外文名称（如有）": "外文名称",
    "公司的外文名称缩写（如有）": "外文缩写",
    "公司的法定代表人": "法定代表人",
    "注册地址": "注册地址",
    "公司注册地址": "注册地址",
    "办公地址": "办公地址",
    "公司办公地址": "办公地址",
}
URL_PATTERN = re.compile(r"https?://[^\s，。]+")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _extract_company_info(pages: list[str]) -> dict[str, str]:
    """从年报前若干页抓取公司档案（最佳努力）。"""
    info: dict[str, str] = {}
    for text in pages[:20]:
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if "邮政编码" in line or "历史变更" in line:
                continue
            if "公司网址" in line and "网址" not in info:
                url = URL_PATTERN.search(line)
                if url:
                    info["网址"] = url.group(0)[:80]
            if ("电子信箱" in line or "电子邮箱" in line) and "邮箱" not in info:
                email = EMAIL_PATTERN.search(line)
                if email:
                    info["邮箱"] = email.group(0)[:80]
            for label, key in INFO_LABELS.items():
                if key in info or not line.startswith(label):
                    continue
                value = line[len(label):].lstrip(" ：:").rstrip(" 。")
                value = value[:80]
                if len(value) >= 2:
                    info[key] = value
        if {"全称", "注册地址", "法定代表人", "网址", "邮箱"} <= set(info):
            break
    return info


FIRST_ROW_ANCHORS = {
    "balance": ("货币资金",),
    "income": ("营业总收入", "营业收入"),
    "cashflow": ("销售商品",),
}
ROW_LINE = re.compile(
    r"^(?P<label>[^\d]{2,40}?)\s+(?P<current>\(?-?[\d,]+(?:\.\d{2})?\)?)\s+"
    r"(?P<previous>\(?-?[\d,]+(?:\.\d{2})?\)?)\s*$"
)


def _recover_first_rows(rows: dict[str, list[StatementRow]], pages: list[str], ranges: dict[str, tuple[int, int]]) -> dict[str, list[StatementRow]]:
    """报表首行被并进表头时，用起始页文本把锚点科目补回第一行。"""
    for kind, (start, _end) in ranges.items():
        items = rows.get(kind, [])
        anchors = FIRST_ROW_ANCHORS.get(kind, ())
        if not items or not anchors:
            continue
        first_page = min(row.page for row in items)
        if any(
            anchor in row.label
            for row in items
            if row.page <= first_page + 1
            for anchor in anchors
        ):
            continue
        for page_number in (start, start + 1):
            if page_number < 1 or page_number > len(pages):
                continue
            for line in pages[page_number - 1].splitlines():
                flat = " ".join(line.split())
                match = ROW_LINE.match(flat)
                if not match or not any(anchor in match.group("label") for anchor in anchors):
                    continue
                try:
                    current = normalize(match.group("current")).value
                    previous = normalize(match.group("previous")).value
                except Exception:
                    continue
                if current is None:
                    continue
                cells = [CellValue(match.group("current"), current, "current", page_number, (0.0, 0.0, 0.0, 0.0))]
                if previous is not None:
                    cells.append(CellValue(match.group("previous"), previous, "previous", page_number, (0.0, 0.0, 0.0, 0.0)))
                items.insert(
                    0,
                    StatementRow(
                        label=match.group("label").strip(),
                        page=page_number,
                        snippet=flat[:200],
                        cells=tuple(cells),
                        is_missing=False,
                    ),
                )
                rows[kind] = items
                break
            else:
                continue
            break
    return rows


CASH_LINE = re.compile(r"^货币资金\s+(?P<current>\(?-?[\d,]+\.\d{2}\)?)\s+(?P<previous>\(?-?[\d,]+\.\d{2}\)?)")


def _add_cash_fallback(rows: dict[str, list[StatementRow]], pages: list[str]) -> dict[str, list[StatementRow]]:
    """部分年报首页表格首行会被并表头，导致「货币资金」缺失：从页面文本补回。"""
    balance_rows = rows.get("balance", [])
    if balance_rows:
        first_page = min(row.page for row in balance_rows)
        if any(row.label.strip() == "货币资金" and row.page <= first_page + 1 for row in balance_rows):
            return rows
    first_page = min((row.page for row in balance_rows), default=1)
    for index in (first_page, first_page + 1):
        if index < 1 or index > len(pages):
            continue
        for line in pages[index - 1].splitlines():
            match = CASH_LINE.match(" ".join(line.split()))
            if not match:
                continue
            try:
                current = normalize(match.group("current")).value
                previous = normalize(match.group("previous")).value
            except Exception:
                continue
            if current is None:
                continue
            cells = [CellValue(match.group("current"), current, "current", index, (0.0, 0.0, 0.0, 0.0))]
            if previous is not None:
                cells.append(CellValue(match.group("previous"), previous, "previous", index, (0.0, 0.0, 0.0, 0.0)))
            rows.setdefault("balance", []).insert(
                0,
                StatementRow(label="货币资金", page=index, snippet=line.strip()[:200], cells=tuple(cells), is_missing=False),
            )
            return rows
    return rows


def _collect_page_texts(rows: dict[str, list[StatementRow]], pages: list[str]) -> dict[int, str]:
    """保留三表所在页的文本，供溯源浮层展示整页原文。"""
    numbers = sorted({row.page for items in rows.values() for row in items})
    result: dict[int, str] = {}
    for number in numbers:
        if 1 <= number <= len(pages):
            result[number] = pages[number - 1][:1500]
    return result


def build_filing(pdf_path: str | Path, period: str, filing_id: str = "f_01") -> FilingData:
    """把一份财报 PDF 变成看板需要的数据（定位 → 表格 → 指标 → 勾稽 → 异常）。"""
    path = str(pdf_path)
    with PdfDoc(path) as doc:
        page_count = doc.page_count
        pages = [doc.page_text(index) for index in range(1, page_count + 1)]

    located = locate_statements(pages)
    starts = {
        "income": located.income.start,
        "balance": located.balance.start,
        "cashflow": located.cashflow.start,
    }
    ordered = sorted(starts.values())
    ranges = {
        kind: (
            starts[kind],
            ordered[ordered.index(starts[kind]) + 1] - 1
            if ordered.index(starts[kind]) + 1 < len(ordered)
            else min(starts[kind] + 2, page_count),
        )
        for kind in starts
    }

    rows = extract_statement_rows(path, ranges)
    rows = _add_deducted_fallback(rows, pages)
    rows = _recover_first_rows(rows, pages, ranges)
    values = values_from_rows(rows)
    metrics = compute_metrics(values)
    checks = check_statements(values)
    anomalies = detect(values, {item.code: item for item in metrics}, checks, pages_from_rows(rows))

    return FilingData(
        filing_id=filing_id,
        period=period,
        pages=page_count,
        rows=rows,
        values=values,
        metrics=metrics,
        checks=checks,
        anomalies=anomalies,
        company_info=_extract_company_info(pages),
        page_texts=_collect_page_texts(rows, pages),
    )


def build_session(
    pdf_path: str | Path,
    company_name: str,
    stock_code: str = "",
    period: str = "",
    session_id: str = "s_demo",
) -> SessionData:
    """单期会话；多期通过 append_filing 追加。"""
    filing = build_filing(pdf_path, period or "2024", "f_01")
    return SessionData(
        session_id=session_id,
        company_name=company_name,
        stock_code=stock_code,
        filings=[filing],
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def company_key(name: str) -> str:
    """公司归一：去掉代码前缀、年份、报告名与扩展名，便于判断「同一公司」。"""
    import re

    value = re.sub(r"^\d{6}[_-]", "", name)
    value = re.sub(r"20\d{2}", "", value)
    value = re.sub(r"[_-]?年?年度报告", "", value)
    value = re.sub(r"\.pdf$", "", value, flags=re.IGNORECASE)
    return value.strip("_- ").strip()


def append_filing(session: SessionData, filing: FilingData, max_filings: int = 5) -> SessionData:
    """把新一期追加进会话；重复期间 / 超期数 / 公司不一致都显式报错。"""
    from core.errors import AppError, ErrorCode

    if len(session.filings) >= max_filings:
        raise AppError(
            ErrorCode.SESSION_FULL,
            "会话期数已达上限",
            {"max_filings": max_filings},
        )
    if any(item.period == filing.period for item in session.filings):
        raise AppError(
            ErrorCode.SESSION_MISMATCH,
            "报告期已存在",
            {"period": filing.period, "reason": "duplicate_period"},
        )
    filings = sorted(session.filings + [filing], key=lambda item: item.period)
    return SessionData(
        session_id=session.session_id,
        company_name=session.company_name,
        stock_code=session.stock_code,
        filings=filings,
        created_at=session.created_at,
    )
