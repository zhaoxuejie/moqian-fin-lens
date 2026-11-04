from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    OK = 0

    INVALID_FILE_TYPE = 40001
    FILE_TOO_LARGE = 40002
    TOO_MANY_PAGES = 40003
    SESSION_MISMATCH = 40004
    SESSION_FULL = 40005
    INVALID_PARAMS = 40006

    SESSION_FORBIDDEN = 40301

    NOT_FOUND = 40400
    SESSION_NOT_FOUND = 40401
    JOB_NOT_FOUND = 40402

    FILING_NOT_READY = 40901

    PARSE_FAILED = 42201
    STATEMENT_LOCATE_FAILED = 42202
    UNSUPPORTED_REPORT_TYPE = 42203

    RATE_LIMITED = 42901

    INTERNAL = 50001
    QUEUE_FULL = 50301


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.OK: 200,
    ErrorCode.INVALID_FILE_TYPE: 400,
    ErrorCode.FILE_TOO_LARGE: 400,
    ErrorCode.TOO_MANY_PAGES: 400,
    ErrorCode.SESSION_MISMATCH: 400,
    ErrorCode.SESSION_FULL: 400,
    ErrorCode.INVALID_PARAMS: 400,
    ErrorCode.SESSION_FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.FILING_NOT_READY: 409,
    ErrorCode.PARSE_FAILED: 422,
    ErrorCode.STATEMENT_LOCATE_FAILED: 422,
    ErrorCode.UNSUPPORTED_REPORT_TYPE: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL: 500,
    ErrorCode.QUEUE_FULL: 503,
}


def http_status(code: ErrorCode) -> int:
    return _HTTP_STATUS.get(code, 500)


class AppError(Exception):
    """业务异常：统一由异常处理器转成 {code,msg,data,request_id} 结构。"""

    def __init__(
        self,
        code: ErrorCode,
        msg: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.msg = msg
        self.detail = detail or {}
        super().__init__(msg)
