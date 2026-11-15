import pytest

from apps.common import health

pytestmark = pytest.mark.django_db


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_when_database_and_redis_are_up(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_redis_failure_without_details(client, monkeypatch):
    def broken(*_args, **_kwargs):
        raise ConnectionError("redis down at redis://secret-host")

    monkeypatch.setattr(health.redis.Redis, "from_url", broken)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_readyz_reports_database_failure(client, monkeypatch):
    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(health, "connection", BrokenConnection())
    response = client.get("/readyz")
    assert response.status_code == 503


def test_health_endpoints_are_get_only(client):
    assert client.post("/healthz").status_code == 405
