from __future__ import annotations

import logging
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import ConfigError, Settings, load_settings
from core.context import request_id_var
from core.errors import AppError, ErrorCode, http_status
from core.logging import get_logger, log_event, setup_logging
from core.response import fail
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
