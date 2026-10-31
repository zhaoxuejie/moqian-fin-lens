from __future__ import annotations

from typing import Any

from core.context import current_request_id


def ok(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "msg": "ok", "data": data, "request_id": current_request_id()}


def fail(
    code: int,
    msg: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": int(code),
        "msg": msg,
        "data": None,
        "request_id": current_request_id(),
    }
    if detail:
        body["detail"] = detail
    return body
