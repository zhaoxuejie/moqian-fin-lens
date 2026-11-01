from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024
_LOCK = threading.Lock()


def append_run(log_path: Path, record: dict) -> None:
    """向运行摘要追加一行 JSON；超过 5MB 时轮转一次。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), **record}
    with _LOCK:
        if log_path.exists() and log_path.stat().st_size > _MAX_BYTES:
            rotated = log_path.with_suffix(log_path.suffix + ".1")
            if rotated.exists():
                rotated.unlink()
            log_path.rename(rotated)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def success_rate(total: int, failed: int) -> float:
    if total <= 0:
        return 1.0
    return (total - failed) / total


def should_alert(total: int, failed: int, threshold: float = 0.9, min_samples: int = 10) -> bool:
    return total >= min_samples and success_rate(total, failed) < threshold
