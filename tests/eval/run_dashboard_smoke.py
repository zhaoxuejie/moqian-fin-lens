"""真实数据冒烟：用评估集一份年报构建会话，验证页面与 5 个接口。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_dashboard_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from core.config import Settings  # noqa: E402
from dashboard.session import build_session  # noqa: E402

PDF = Path(__file__).resolve().parent / "pdf" / "002230_科大讯飞" / "002230_科大讯飞_2024年年度报告.pdf"


def main() -> int:
    if not PDF.exists():
        print("缺少评估集 PDF")
        return 2

    started = time.perf_counter()
    session = build_session(PDF, "科大讯飞股份有限公司", "002230.SZ", "2024", "s_002230")
    build_seconds = time.perf_counter() - started

    settings = Settings(database_path="./data/smoke.db", data_dir="./data", _env_file=None)
    application = create_app(settings)
    application.state.sessions[session.session_id] = session
    client = TestClient(application)

    page = client.get("/s/s_002230")
    detail = client.get("/api/v1/sessions/s_002230")
    statements = client.get("/api/v1/sessions/s_002230/statements")
    metrics = client.get("/api/v1/sessions/s_002230/metrics")
    charts = client.get("/api/v1/sessions/s_002230/charts")
    anomalies = client.get("/api/v1/sessions/s_002230/anomalies")
    trace = client.get("/api/v1/sessions/s_002230/trace/row:income:0")
    created = client.post("/api/v1/sessions/s_002230/exports", json={"kind": "markdown"})
    download = client.get(created.json()["data"]["download_url"]) if created.status_code == 200 else None

    print(f"build_session: {build_seconds:.1f}s, pages={session.latest.pages}")
    print(f"page: {page.status_code}, charts={len(charts.json()['data']['charts'])}")
    print(f"metrics={len(metrics.json()['data']['metrics'])}, statements={len(statements.json()['data']['statements'])}")
    print(f"anomalies={len(anomalies.json()['data']['items'])}")
    print("checks:", [item["status"] for item in detail.json()["data"]["checks"]])
    print(f"trace: {trace.status_code}, page={trace.json()['data']['page']}")
    print(f"export: {created.status_code}, bytes={len(download.content) if download is not None else 0}")

    ok = (
        page.status_code == 200
        and len(charts.json()["data"]["charts"]) == 11
        and len(metrics.json()["data"]["metrics"]) == 20
        and trace.status_code == 200
        and created.status_code == 200
        and download is not None
        and download.status_code == 200
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
