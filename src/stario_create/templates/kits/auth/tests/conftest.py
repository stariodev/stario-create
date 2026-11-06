import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from stario import json
from stario.testing import TestClient

from app.common.oidc import Http
from app.features.login.urls import LOGIN_CALLBACK, LOGIN_START
from app.main import bootstrap

ISSUER = "https://issuer.test"


class FakeIssuer(Http):
    """Discovery and the token endpoint. The code is "<email> <nonce>": the
    email signs in, and the nonce goes into the ID token."""

    async def get_json(self, url: str) -> dict[str, Any]:
        assert url == f"{ISSUER}/.well-known/openid-configuration"
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
        }

    async def post_form(
        self, url: str, form: dict[str, str], headers: dict[str, str]
    ) -> dict[str, Any]:
        assert headers["Authorization"].startswith("Basic ")
        email, nonce = form["code"].split(" ")
        claims = {
            "iss": ISSUER,
            "aud": "client-id",
            "sub": f"sub-{email}",
            "email": email,
            "email_verified": True,
            "exp": time.time() + 60,
            "nonce": nonce,
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return {"id_token": f"header.{payload}.signature", "access_token": "token"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-test-secret-test-secret-test")
    monkeypatch.setenv("APP_DEV", "1")
    monkeypatch.setenv("LOGIN_ISSUER", ISSUER)
    monkeypatch.setenv("LOGIN_CLIENT_ID", "client-id")
    monkeypatch.setenv("LOGIN_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("app.main.Http", FakeIssuer)
    return monkeypatch


@pytest.fixture
async def client(env):
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c


async def start(client, next_url="/") -> dict[str, str]:
    """POST the login button; return the query of the redirect to the issuer."""
    r = await client.post(LOGIN_START.href(), data={"next": next_url}, follow_redirects=False)
    assert r.status_code == 303
    return {k: v[0] for k, v in parse_qs(urlsplit(str(r.headers.get("location"))).query).items()}


async def login(client, email="ada@example.com", next_url="/"):
    """Sign in as the issuer would: the start, then the callback with a code."""
    query = await start(client, next_url)
    code = f"{email} {query['nonce']}"
    return await client.get(
        LOGIN_CALLBACK.href(),
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )
