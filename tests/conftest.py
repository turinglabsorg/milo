import pytest
from fastapi.testclient import TestClient

from milo.app import create_app
from milo.store import Store


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
