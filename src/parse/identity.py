from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

IDENTITY_PAGES = 10

# 深交所：「股票简称 科大讯飞 股票代码 002230」；上交所科创板：「公司代码：688111 公司简称：金山办公」
CODE = re.compile(r"(?:股票|公司|证券)代码[:：]?\s*(\d{6})(?!\d)")
NAME = re.compile(r"(?:股票|公司|证券)简称[:：]?\s*([*A-Za-z一-龥]{2,12})")
NAME_STOPWORDS = ("代码", "简称", "股票", "变更")
# 页眉「2024 年年度报告」「2025 年半年度报告」每页都有；正文里「已披露季度报告、半年度报告」前面没有年份，不会命中
TITLE = re.compile(r"(20\d{2})\s*年\s*(半年度|年度)报告")


@dataclass(frozen=True)
class ReportIdentity:
    stock_code: str | None
    short_name: str | None
    year: str | None
    report_type: str | None  # annual | semi


def identify_report(pages: Sequence[str]) -> ReportIdentity:
    """从年报前 10 页正文识别证券代码、简称、报告年度与报告类型；识别不到的字段为 None。"""
    code: str | None = None
    name: str | None = None
    titles: Counter[tuple[str, str]] = Counter()
    for text in pages[:IDENTITY_PAGES]:
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if code is None and (match := CODE.search(line)):
                code = match.group(1)
            if name is None:
                for match in NAME.finditer(line):
                    value = match.group(1)
                    if not any(word in value for word in NAME_STOPWORDS):
                        name = value
                        break
            for year, kind in TITLE.findall(line):
                titles[(year, kind)] += 1

    year = report_type = None
    if titles:
        (year, kind), _count = titles.most_common(1)[0]
        report_type = "semi" if kind == "半年度" else "annual"
    return ReportIdentity(stock_code=code, short_name=name, year=year, report_type=report_type)
