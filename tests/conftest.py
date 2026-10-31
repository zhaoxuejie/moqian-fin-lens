import pytest

from core.config import Settings


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "app.db"),
        data_dir=str(tmp_path),
        _env_file=None,
    )


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client
