from __future__ import annotations

import re

SECTION_PREFIX = re.compile(r"^[一二三四五六七八九十]+、")
ARABIC_SECTION = re.compile(r"^（[一二三四五六七八九十]+）")
LABEL = re.compile(r"^([\u4e00-\u9fa5（）()、：:]{2,30})")
PROSE_MARKS = "。，；！？"

STOPWORDS = {
    "项目",
    "附注",
    "单位",
    "币种",
    "编制单位",
    "法定代表人",
    "主管会计工作负责人",
    "会计机构负责人",
    "年初余额",
    "年末余额",
    "期末余额",
    "期初余额",
    "本期发生额",
    "上期发生额",
    "本年金额",
    "上年金额",
    "流动资产",
    "非流动资产",
    "流动负债",
    "非流动负债",
    "所有者权益",
    "股东权益",
}


def extract_labels(text: str) -> list[str]:
    """从报表页文本里按行提取「疑似科目名」，保持出现顺序并去重。

    只取形如「科目名 数字…」的行；剔除以序号开头的分组标题、叙述性长句与表头词。
    """
    labels: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or any(mark in line for mark in PROSE_MARKS):
            continue
        if SECTION_PREFIX.match(line) or ARABIC_SECTION.match(line):
            continue
        match = LABEL.match(line)
        if not match:
            continue
        label = match.group(1).rstrip("：:")
        if len(label) < 2 or label in STOPWORDS or label in seen:
            continue
        remainder = line[len(match.group(1)):].strip()
        if remainder and remainder[0] not in "0123456789(-—－（":
            continue
        seen.add(label)
        labels.append(label)
    return labels
