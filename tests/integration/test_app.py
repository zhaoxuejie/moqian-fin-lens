from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app
from core.errors import AppError, ErrorCode


def test_healthz(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_html_and_disclaimer(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "免责声明" in response.text


def test_unknown_route_returns_envelope(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/no-such-page")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 40400
    assert body["data"] is None
    assert body["request_id"]


def test_request_id_is_echoed_and_unique(settings):
    with TestClient(create_app(settings)) as client:
        first = client.get("/healthz", headers={"X-Request-Id": "fixed-1"})
        second = client.get("/healthz")

    assert first.headers["X-Request-Id"] == "fixed-1"
    assert second.headers["X-Request-Id"] != "fixed-1"


def test_database_file_is_created(settings):
    create_app(settings)
    assert Path(settings.database_path).exists()


def test_app_error_is_converted_to_envelope(settings):
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise AppError(ErrorCode.PARSE_FAILED, "解析失败", {"page": 3})

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == int(ErrorCode.PARSE_FAILED)
    assert body["detail"] == {"page": 3}
    assert body["data"] is None


def test_bootstrap_exits_when_config_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main_module._bootstrap()

    assert exc_info.value.code == 2


def test_lazy_app_attribute_builds_asgi_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "lazy.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    built = main_module.__getattr__("app")

    assert isinstance(built, FastAPI)


def test_unknown_attribute_raises():
    with pytest.raises(AttributeError):
        main_module.__getattr__("nope")
