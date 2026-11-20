from unittest.mock import MagicMock

import psycopg
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_successful_database_probe(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    connect = MagicMock()
    monkeypatch.setattr(psycopg, "connect", connect)

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    connect.assert_called_once_with("postgresql://test", connect_timeout=5, autocommit=True)
    connection = connect.return_value.__enter__.return_value
    connection.execute.assert_called_once_with("SELECT 1")


def test_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert client.get("/health/db").status_code == 503
    assert client.get("/health").status_code == 200


def test_failed_connection_hides_driver_details(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    connect = MagicMock(side_effect=psycopg.OperationalError("private driver detail"))
    monkeypatch.setattr(psycopg, "connect", connect)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "DB에 연결할 수 없습니다."}
