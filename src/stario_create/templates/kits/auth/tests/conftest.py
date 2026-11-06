import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from stario import json
from stario.testing import TestClient

from app.common.providers import GOOGLE, Http
from app.features.login.urls import LOGIN_CALLBACK, LOGIN_START
from app.main import bootstrap


class FakeProviders(Http):
    """Google and GitHub. The code is "<email> <nonce>": that email signs in,
    and the nonce goes into the Google ID token."""

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        if url == f"{GOOGLE}/.well-known/openid-configuration":
            return {
                "issuer": GOOGLE,
                "authorization_endpoint": f"{GOOGLE}/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
            }
        email = (headers or {})["Authorization"].removeprefix("Bearer ")
        if url == "https://api.github.com/user":
            return {"id": len(email), "login": email.split("@")[0], "name": None}
        assert url == "https://api.github.com/user/emails"
        return [{"email": email, "primary": True, "verified": True}]

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        email, nonce = form["code"].split(" ")
        if url == "https://github.com/login/oauth/access_token":
            return {"access_token": email}
        assert headers["Authorization"].startswith("Basic ")
        claims = {
            "iss": GOOGLE,
            "aud": "google-id",
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
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "github-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "github-secret")
    monkeypatch.setattr("app.main.Http", FakeProviders)
    return monkeypatch


@pytest.fixture
async def client(env):
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c


async def start(client, provider="google", next_url="/") -> dict[str, str]:
    """POST a login button; return the query of the redirect to the provider."""
    r = await client.post(
        LOGIN_START.href(provider), data={"next": next_url}, follow_redirects=False
    )
    assert r.status_code == 303
    return {k: v[0] for k, v in parse_qs(urlsplit(str(r.headers.get("location"))).query).items()}


async def login(client, email="ada@example.com", provider="google", next_url="/"):
    """Sign in as the provider would: the start, then the callback with a code."""
    query = await start(client, provider, next_url)
    code = f"{email} {query.get('nonce', '-')}"
    return await client.get(
        LOGIN_CALLBACK.href(provider),
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )
