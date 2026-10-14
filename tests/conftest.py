import os
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from milo.app import create_app
from milo.store import Store


@pytest.fixture(autouse=True)
def postgres(monkeypatch):
    """Every archive directory gets its own throwaway PostgreSQL database."""
    admin = os.environ.get("MILO_TEST_DATABASE_URL")
    if not admin:
        pytest.skip("Set MILO_TEST_DATABASE_URL to a PostgreSQL server for tests")
    created = {}

    live = os.environ.get("MILO_LIVE_TEST_DATA")

    def resolve(directory):
        key = str(Path(directory).resolve())
        # Browser tests against the separately started CI service share its database.
        if live and key == str(Path(live).resolve()) and os.environ.get("MILO_DATABASE_URL"):
            return os.environ["MILO_DATABASE_URL"]
        if key not in created:
            name = "milo_test_" + uuid.uuid4().hex[:16]
            with psycopg.connect(admin, autocommit=True) as connection:
                connection.execute(f"CREATE DATABASE {name}")
            created[key] = psycopg.conninfo.make_conninfo(admin, dbname=name)
        return created[key]

    monkeypatch.setattr("milo.store.database_url", resolve)
    yield
    with psycopg.connect(admin, autocommit=True) as connection:
        for dsn in created.values():
            connection.execute(f"DROP DATABASE IF EXISTS {psycopg.conninfo.conninfo_to_dict(dsn)['dbname']} WITH (FORCE)")


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "data")
    yield value
    value.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def logged_in(client):
    response = client.post("/api/setup", json={"password": "a secure test passphrase",
                                               "bootstrap": client.app.state.store.bootstrap})
    assert response.status_code == 200
    return client


@pytest.fixture
def account_data():
    return {"name": "Personal", "email": "you@example.com", "username": "you@example.com",
            "password": "app-password-must-stay-private", "imap_host": "imap.example.com", "imap_port": 993,
            "smtp_host": "smtp.example.com", "smtp_port": 465, "smtp_security": "tls", "color": "#afa4ff"}
