from __future__ import annotations

from anomaly.rules import AnomalyItem


def build_anomaly_payload(items: list[AnomalyItem]) -> list[dict[str, object]]:
    return [
        {
            "rule_code": item.rule_code,
            "title": item.title,
            "text": item.text,
            "evidence": item.evidence,
            "page_refs": item.page_refs,
        }
        for item in items
    ]


def session_yoy(filings) -> dict[str, dict[str, object]]:
    """会话级同比：最新一期 vs 上一期；金额类给百分比，比率类给百分点。"""
    if len(filings) < 2:
        return {}
    latest, previous = filings[-1], filings[-2]
    prev_metrics = {item.code: item for item in previous.metrics}
    result: dict[str, dict[str, object]] = {}
    for item in latest.metrics:
        old = prev_metrics.get(item.code)
        if item.value is None or old is None or old.value is None:
            continue
        if item.unit == "%":
            result[item.code] = {"value": str(item.value - old.value), "unit": "pct"}
        elif old.value != 0 and old.value > 0:
            result[item.code] = {
                "value": str((item.value - old.value) / abs(old.value) * 100),
                "unit": "%",
            }
    return result
