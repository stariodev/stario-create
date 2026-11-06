import base64
import hashlib
import time
import zlib
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from stario import json
from stario.testing import TestClient

from app.common.providers import GOOGLE, Http
from app.features.login.urls import LOGIN_CALLBACK, LOGIN_START
from app.main import bootstrap


class FakeProviders(Http):
    """Google and GitHub, with the checks they make. The code carries what the
    provider remembers from the redirect: "<email> <nonce> <challenge> <redirect_uri>".
    An email that starts with "unverified+" comes back unverified, and GitHub
    refuses a code for an email that starts with "refuse+"."""

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        if url == f"{GOOGLE}/.well-known/openid-configuration":
            return {
                "issuer": GOOGLE,
                "authorization_endpoint": f"{GOOGLE}/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
            }
        raw = (headers or {})["Authorization"].removeprefix("Bearer ")
        email = raw.removeprefix("unverified+")
        if url == "https://api.github.com/user":
            return {"id": zlib.crc32(email.encode()), "login": email.split("@")[0], "name": None}
        assert url == "https://api.github.com/user/emails"
        return [{"email": email, "primary": True, "verified": raw == email}]

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        raw, nonce, challenge, redirect_uri = form["code"].split(" ")
        digest = hashlib.sha256(form["code_verifier"].encode()).digest()
        assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == challenge
        assert form["redirect_uri"] == redirect_uri
        if url == "https://github.com/login/oauth/access_token":
            assert (form["client_id"], form["client_secret"]) == ("github-id", "github-secret")
            if raw.startswith("refuse+"):
                return {"error": "bad_verification_code"}
            return {"access_token": raw}
        assert url == "https://oauth2.googleapis.com/token"
        basic = base64.b64encode(b"google-id:google-secret").decode()
        assert headers["Authorization"] == f"Basic {basic}"
        email = raw.removeprefix("unverified+")
        claims = {
            "iss": GOOGLE,
            "aud": "google-id",
            "sub": f"sub-{raw}",
            "email": email,
            "email_verified": raw == email,
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
    parts = [email, query.get("nonce", "-"), query["code_challenge"], query["redirect_uri"]]
    return await client.get(
        LOGIN_CALLBACK.href(provider),
        params={"code": " ".join(parts), "state": query["state"]},
        follow_redirects=False,
    )
