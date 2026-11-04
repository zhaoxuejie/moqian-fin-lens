from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dashboard.session import build_filing

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval" / "pdf"


def test_parallel_parsing_does_not_crash():
    """解析任务在线程池里并发跑（ADR-004，默认 5 并发）；pdfium 并发调用曾直接让进程崩溃。"""
    pdfs = sorted(EVAL_DIR.rglob("*年度报告.pdf"))[:5]
    if len(pdfs) < 5:
        pytest.skip("缺少评估集 PDF")
    with ThreadPoolExecutor(max_workers=5) as pool:
        filings = list(pool.map(lambda path: build_filing(path, path.stem.split("_")[2][:4]), pdfs))
    assert all(filing.metrics for filing in filings)
