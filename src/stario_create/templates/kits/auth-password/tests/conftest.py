import pytest
from stario.testing import TestClient

from app.common.session import hash_password
from app.features.login.urls import LOGIN_POST
from app.main import bootstrap


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-test-secret-test-secret-test")
    monkeypatch.setenv("APP_DEV", "1")
    monkeypatch.setenv("LOGIN_ACCOUNTS", f"Ada@example.com:{hash_password('correct-horse')}")
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c


async def login(client, email="ada@example.com", password="correct-horse") -> str:
    r = await client.post(LOGIN_POST.href(), json={"email": email, "password": password})
    return r.text
