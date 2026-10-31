"""本地预览：用一份真实年报构建会话并启动服务，便于人工或截图验收。

用法：
    .venv\\Scripts\\python.exe tests/eval/run_dashboard_preview.py [port]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import uvicorn  # noqa: E402

from app.main import create_app  # noqa: E402
from core.config import Settings  # noqa: E402
from dashboard.session import build_session  # noqa: E402

PDF = Path(__file__).resolve().parent / "pdf" / "002230_科大讯飞" / "002230_科大讯飞_2024年年度报告.pdf"


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8017
    session = build_session(PDF, "科大讯飞股份有限公司", "002230.SZ", "2024", "s_demo")
    settings = Settings(database_path="./data/preview.db", data_dir="./data", _env_file=None)
    application = create_app(settings)
    application.state.sessions[session.session_id] = session
    print(f"preview: http://127.0.0.1:{port}/s/s_demo")
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
