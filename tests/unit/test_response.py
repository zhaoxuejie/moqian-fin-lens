from core.context import request_id_var
from core.response import fail, ok


def _with_request_id(value: str):
    return request_id_var.set(value)


def test_ok_envelope():
    token = _with_request_id("req-1")
    try:
        assert ok({"a": 1}) == {
            "code": 0,
            "msg": "ok",
            "data": {"a": 1},
            "request_id": "req-1",
        }
    finally:
        request_id_var.reset(token)


def test_fail_envelope_with_detail():
    token = _with_request_id("req-2")
    try:
        body = fail(40001, "文件类型不合法", {"ext": ".docx"})
    finally:
        request_id_var.reset(token)

    assert body["code"] == 40001
    assert body["msg"] == "文件类型不合法"
    assert body["data"] is None
    assert body["detail"] == {"ext": ".docx"}
    assert body["request_id"] == "req-2"


def test_fail_envelope_without_detail():
    body = fail(50001, "服务内部错误")
    assert "detail" not in body
    assert body["code"] == 50001
