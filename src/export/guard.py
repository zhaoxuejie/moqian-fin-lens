from __future__ import annotations

import re

BANNED_WORDS = (
    "买入",
    "卖出",
    "看好",
    "低估",
    "高估",
    "目标价",
    "建议持有",
    "建议买入",
    "建议卖出",
    "强烈推荐",
)


def find_banned(text: str) -> list[str]:
    return [word for word in BANNED_WORDS if word in text]


def assert_clean(text: str) -> None:
    hits = find_banned(text)
    if hits:
        raise ValueError("导出文本包含禁用词：" + "、".join(hits))


WORD = re.compile(r"[\u4e00-\u9fa5]{2,}")
