from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import ConfigError, Settings, load_settings
from core.context import request_id_var
from core.errors import AppError, ErrorCode, http_status
from core.logging import get_logger, log_event, setup_logging
from core.response import fail, ok
from dashboard.build import build_anomaly_payload, build_charts
from dashboard.session import SessionData, build_filing, filter_rows_by_statement
from export.markdown import write_markdown
from export.xlsx import render_xlsx
from jobs.manager import Job, JobManager, RateLimiter
from parse import PdfDoc
from traceability.service import trace_entry
from store.db import Database

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    setup_logging(settings.log_level)
    logger = get_logger()

    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    applied = db.migrate()
    log_event(
        logger,
        logging.INFO,
        "database_ready",
        path=settings.database_path,
        migrations_applied=applied,
    )

    app = FastAPI(title="财报透视（finance-agent）", version="0.1.0")
    app.state.settings = settings
    app.state.db = db
    app.state.sessions = {}
    app.state.exports = {}
    app.state.export_dir = Path(settings.data_dir) / "exports"
    app.state.export_dir.mkdir(parents=True, exist_ok=True)
    app.state.tmp_dir = Path(settings.data_dir) / "tmp"
    app.state.tmp_dir.mkdir(parents=True, exist_ok=True)
    app.state.jobs = JobManager(max_workers=5)
    app.state.limiter = RateLimiter(limit=10, window_seconds=3600)

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                logging.ERROR,
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed,
            )
            request_id_var.reset(token)
            raise

        elapsed = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-Id"] = rid
        log_event(
            logger,
            logging.INFO,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=elapsed,
        )
        request_id_var.reset(token)
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_env": settings.app_env},
        )

    def _session(session_id: str):
        session = app.state.sessions.get(session_id)
        if session is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, "会话不存在", {"session_id": session_id})
        return session

    @app.get("/s/{session_id}")
    async def dashboard(request: Request, session_id: str):
        session = _session(session_id)
        filing = session.latest
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "session": session,
                "filing": filing,
                "metrics": filing.metrics,
                "anomalies": filing.anomalies,
                "rows": filter_rows_by_statement(filing.rows),
                "periods": session.periods,
            },
        )

    @app.get("/api/v1/sessions/{session_id}")
    async def session_detail(session_id: str):
        session = _session(session_id)
        filing = session.latest
        return ok(
            {
                "session_id": session.session_id,
                "company_name": session.company_name,
                "stock_code": session.stock_code,
                "filing_count": len(session.filings),
                "created_at": session.created_at,
                "filings": [
                    {
                        "filing_id": filing.filing_id,
                        "report_type": "annual",
                        "period": filing.period,
                        "status": "done",
                        "pages": filing.pages,
                    }
                ],
                "checks": [
                    {"rule": check.rule, "status": check.status, "diff": str(check.diff) if check.diff is not None else None}
                    for check in filing.checks
                ],
                "unaligned_count": 0,
            }
        )

    @app.get("/api/v1/sessions/{session_id}/statements")
    async def statements(session_id: str, kind: str | None = None):
        session = _session(session_id)
        filing = session.latest
        kinds = [kind] if kind else ["income", "balance", "cashflow"]
        payload = []
        for name in kinds:
            rows = filter_rows_by_statement(filing.rows).get(name, [])
            payload.append(
                {
                    "kind": name,
                    "unit": "元",
                    "rows": [
                        {
                            "entry_id": f"row:{name}:{index}",
                            "label": row.label,
                            "value": None if not row.cells else str(row.cells[0].value),
                            "page": row.page,
                            "snippet": row.snippet,
                            "missing_reason": None if row.cells else "原文未披露",
                        }
                        for index, row in enumerate(rows)
                    ],
                }
            )
        return ok({"filing_id": filing.filing_id, "period": filing.period, "statements": payload})

    @app.get("/api/v1/sessions/{session_id}/metrics")
    async def metrics_api(session_id: str):
        session = _session(session_id)
        filing = session.latest
        return ok(
            {
                "filing_id": filing.filing_id,
                "metrics": [
                    {
                        "code": item.code,
                        "label": item.label,
                        "value": None if item.value is None else str(item.value),
                        "unit": item.unit,
                        "formula": item.formula,
                        "missing_reason": item.missing_reason,
                        "yoy": None if item.yoy is None else str(item.yoy),
                        "yoy_unit": item.yoy_unit,
                        "trace": {"entry_id": f"metric:{item.code}"},
                    }
                    for item in filing.metrics
                ],
            }
        )

    @app.get("/api/v1/sessions/{session_id}/charts")
    async def charts_api(session_id: str):
        session = _session(session_id)
        filing = session.latest
        return ok({"charts": build_charts(filing.values, filing.metrics_by_code, session.periods)})

    @app.get("/api/v1/sessions/{session_id}/anomalies")
    async def anomalies_api(session_id: str):
        session = _session(session_id)
        return ok({"items": build_anomaly_payload(session.latest.anomalies)})

    @app.post("/api/v1/uploads")
    async def uploads(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = app.state.limiter.allow(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=fail(
                    int(ErrorCode.RATE_LIMITED),
                    "上传过于频繁，请稍后再试",
                    {"retry_after": retry_after},
                ),
                headers={"Retry-After": str(retry_after)},
            )

        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise AppError(ErrorCode.INVALID_PARAMS, "缺少上传文件", {})

        filename = str(getattr(upload, "filename", "") or "upload.pdf")
        data = await upload.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                "文件超过大小上限",
                {"size": len(data), "max_mb": settings.max_upload_mb},
            )
        if not data[:5].startswith(b"%PDF"):
            raise AppError(ErrorCode.INVALID_FILE_TYPE, "仅支持 PDF 文件", {"filename": filename})

        job_id = f"j_{uuid.uuid4().hex[:8]}"
        temp_path = app.state.tmp_dir / f"{job_id}.pdf"
        temp_path.write_bytes(data)
        try:
            with PdfDoc(str(temp_path)) as doc:
                page_count = doc.page_count
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.PARSE_FAILED, "PDF 无法打开", {"filename": filename}) from exc
        if page_count > settings.max_pages:
            temp_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.TOO_MANY_PAGES,
                "页数超过上限",
                {"pages": page_count, "max_pages": settings.max_pages},
            )

        session_id = str(form.get("session_id") or f"s_{uuid.uuid4().hex[:8]}")
        report_type = "annual" if "年度" in filename else "semi"
        match = re.search(r"(20\d{2})", filename)
        period = match.group(1) if match else "unknown"
        company = filename.rsplit(".", 1)[0]

        job = Job(job_id=job_id, filing_id="f_01", session_id=session_id)
        position = app.state.jobs.create(job)

        def task(progress):
            progress("parsing", 0.15)
            filing = build_filing(temp_path, period, "f_01")
            progress("computing", 0.8)
            return SessionData(
                session_id=session_id,
                company_name=company,
                stock_code="",
                filings=[filing],
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )

        def on_success(session: SessionData) -> None:
            app.state.sessions[session.session_id] = session
            temp_path.unlink(missing_ok=True)

        app.state.jobs.submit(job_id, task, on_success, lambda exc: None)

        return JSONResponse(
            status_code=202,
            content=ok(
                {
                    "session_id": session_id,
                    "filing": {
                        "filing_id": "f_01",
                        "report_type": report_type,
                        "period": period,
                        "status": "queued",
                    },
                    "job": {"job_id": job_id, "state": "queued", "queue_position": position},
                }
            ),
        )

    @app.get("/api/v1/jobs/{job_id}")
    async def job_status(job_id: str):
        job = app.state.jobs.get(job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, "任务不存在", {"job_id": job_id})
        return ok(
            {
                "job_id": job.job_id,
                "state": job.state,
                "progress": job.progress,
                "stage": job.stage,
                "queue_position": job.queue_position,
                "error": job.error,
                "started_at": job.started_at,
            }
        )

    @app.get("/api/v1/sessions/{session_id}/trace/{entry_id}")
    async def trace_api(session_id: str, entry_id: str):
        session = _session(session_id)
        return ok(trace_entry(session, entry_id))

    @app.post("/api/v1/sessions/{session_id}/exports")
    async def create_export(session_id: str, request: Request):
        session = _session(session_id)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        kind = str(payload.get("kind", "markdown"))
        if kind not in ("markdown", "xlsx"):
            raise AppError(ErrorCode.INVALID_PARAMS, "不支持的导出格式", {"kind": kind})

        export_id = f"x_{uuid.uuid4().hex[:8]}"
        suffix = "md" if kind == "markdown" else "xlsx"
        target = app.state.export_dir / f"{session_id}-{export_id}.{suffix}"
        if kind == "markdown":
            write_markdown(session, target)
        else:
            render_xlsx(session, target)

        created = datetime.now().astimezone()
        app.state.exports[export_id] = {
            "session_id": session_id,
            "kind": kind,
            "path": str(target),
            "state": "ready",
            "expires_at": (created + timedelta(hours=1)).isoformat(timespec="seconds"),
        }
        return ok(
            {
                "export_id": export_id,
                "state": "ready",
                "download_url": f"/s/{session_id}/export/{export_id}",
            }
        )

    @app.get("/api/v1/exports/{export_id}")
    async def export_status(export_id: str):
        record = app.state.exports.get(export_id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND, "导出不存在", {"export_id": export_id})
        return ok(
            {
                "export_id": export_id,
                "state": record["state"],
                "download_url": f"/s/{record['session_id']}/export/{export_id}",
                "expires_at": record["expires_at"],
            }
        )

    @app.get("/s/{session_id}/export/{export_id}")
    async def download_export(session_id: str, export_id: str):
        record = app.state.exports.get(export_id)
        if record is None or record["session_id"] != session_id:
            raise AppError(ErrorCode.NOT_FOUND, "导出不存在", {"export_id": export_id})
        media = (
            "text/markdown"
            if record["kind"] == "markdown"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        suffix = "md" if record["kind"] == "markdown" else "xlsx"
        return FileResponse(record["path"], media_type=media, filename=f"{session_id}.{suffix}")

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=http_status(exc.code),
            content=fail(int(exc.code), exc.msg, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=http_status(ErrorCode.INVALID_PARAMS),
            content=fail(int(ErrorCode.INVALID_PARAMS), "请求参数不合法", {"errors": exc.errors()}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INTERNAL
        msg = "接口不存在" if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content=fail(int(code), msg))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error")
        return JSONResponse(
            status_code=http_status(ErrorCode.INTERNAL),
            content=fail(int(ErrorCode.INTERNAL), "服务内部错误"),
        )

    return app


def _bootstrap() -> FastAPI:
    try:
        return create_app()
    except ConfigError as exc:
        fields = ", ".join(exc.fields)
        print(f"[finance-agent] startup failed: missing or invalid config: {fields}", file=sys.stderr)
        raise SystemExit(2) from exc


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """延迟创建 ASGI 应用：uvicorn 读取 `app.main:app` 时才加载配置。

    结果缓存在模块级变量里，避免 uvicorn 多次访问属性时重复建库。
    这样测试可以直接 import create_app，不会被环境变量缺失卡住。
    """
    global _app
    if name == "app":
        if _app is None:
            _app = _bootstrap()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
