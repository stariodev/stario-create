import base64
import sqlite3
import time
from typing import Any

import pytest
from litewriter import LiteWriter
from stario import json
from stario.testing import TestClient

from app.common.providers import GOOGLE, Flow, Http, Issuer, LoginFailed
from app.features.login.data import get_user, schema
from app.features.login.urls import LOGIN, LOGIN_CALLBACK, LOGIN_START, LOGOUT
from app.main import bootstrap
from tests.conftest import FakeProviders, login, start

# The prefix that session.require protects in app/main.py. It has no page yet,
# so a signed-in request gets 404 and a signed-out one gets 303.
PROTECTED = "/app"


def counts(tmp_path) -> tuple[int, int]:
    with sqlite3.connect(tmp_path / "app.sqlite3") as db:
        users = db.execute("SELECT count(*) FROM users").fetchone()[0]
        return users, db.execute("SELECT count(*) FROM identities").fetchone()[0]


async def test_a_protected_page_sends_a_visitor_to_login_and_back(client):
    r = await client.get(f"{PROTECTED}?tab=2", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == f"{LOGIN.href()}?next=%2Fapp%3Ftab%3D2"
    r = await client.get(PROTECTED, headers={"datastar-request": "true"})
    assert "window.location" in r.text
    r = await login(client, next_url=f"{PROTECTED}?tab=2")
    assert r.headers.get("location") == f"{PROTECTED}?tab=2"
    r = await client.get(LOGIN.href(query={"next": "/app/x"}), follow_redirects=False)
    assert r.headers.get("location") == "/app/x"


async def test_the_start_sends_state_nonce_and_pkce(client):
    query = await start(client)
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == f"http://testserver{LOGIN_CALLBACK.href('google')}"
    assert query["state"] and query["nonce"]


async def test_login_then_logout(client):
    assert (await login(client)).headers.get("location") == "/"
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 404
    await client.post(LOGOUT.href(), follow_redirects=False)
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_a_callback_without_the_start_signs_nobody_in(client):
    r = await client.get(
        LOGIN_CALLBACK.href("google"),
        params={"code": "ada@example.com x y z", "state": "forged"},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "expired"})
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_a_callback_for_another_provider_fails(client):
    query = await start(client, "google")
    r = await client.get(
        LOGIN_CALLBACK.href("github"),
        params={"code": "ada@example.com x y z", "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "expired"})


async def test_a_wrong_nonce_fails(client):
    query = await start(client)
    code = f"ada@example.com other {query['code_challenge']} {query['redirect_uri']}"
    r = await client.get(
        LOGIN_CALLBACK.href("google"),
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})


async def test_a_cancel_at_the_provider_says_so(client):
    query = await start(client)
    r = await client.get(
        LOGIN_CALLBACK.href("google"),
        params={"error": "access_denied", "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "denied"})
    assert "cancelled" in (await client.get(r.headers.get("location"))).text


async def test_github_refuses_a_code(client):
    r = await login(client, email="refuse+ada@example.com", provider="github")
    assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})


async def test_a_failed_discovery_fails_the_sign_in(env):
    class Down(FakeProviders):
        async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
            raise LoginFailed("no answer")

    env.setattr("app.main.Http", Down)
    async with TestClient(bootstrap, request_timeout=5) as client:
        r = await client.post(LOGIN_START.href("google"), data={}, follow_redirects=False)
        assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})


async def test_an_outside_next_goes_home(client):
    r = await login(client, next_url="//evil.example")
    assert r.headers.get("location") == "/"


async def test_the_allow_list_keeps_other_accounts_out(env):
    env.setenv("LOGIN_ALLOWED_EMAILS", "ada@example.com")
    async with TestClient(bootstrap, request_timeout=5) as client:
        r = await login(client, email="bob@example.com")
        assert r.headers.get("location") == LOGIN.href(query={"error": "not_allowed"})
        assert (await login(client)).headers.get("location") == "/"


async def test_github_joins_the_google_user_and_two_users_stay_apart(client, tmp_path):
    await login(client, email="ada@example.com", provider="github")
    await login(client, email="ada@example.com", provider="google")
    await login(client, email="bob@example.com", provider="github")
    assert counts(tmp_path) == (2, 3)


async def test_an_unverified_email_never_joins(client, tmp_path):
    await login(client, email="unverified+victim@example.com", provider="google")
    await login(client, email="victim@example.com", provider="github")
    await login(client, email="unverified+ada@example.com", provider="github")
    assert counts(tmp_path) == (3, 3)


async def test_get_user_reads_the_profile(env, tmp_path):
    async with TestClient(bootstrap, request_timeout=5) as client:
        await login(client, email="unverified+eve@example.com", provider="github")
        await login(client, email="ada@example.com", provider="google")
    async with LiteWriter(tmp_path / "app.sqlite3", schema=schema) as db:
        rows = db.query("SELECT id FROM users ORDER BY id")
        eve, ada = (get_user(db, row[0]) for row in rows)
    assert eve is not None and (eve.email, eve.name) == ("", "eve")
    assert ada is not None and ada.email == "ada@example.com"


async def test_an_active_session_slides(client, monkeypatch):
    await login(client)
    later = time.time() + 8 * 24 * 3600
    monkeypatch.setattr("stario.cookies.time.time", lambda: later)
    r = await client.get(PROTECTED, follow_redirects=False)
    assert r.status_code == 404
    assert "session=" in str(r.headers.get("set-cookie"))


class Answers(Http):
    def __init__(self, discovery: dict[str, Any], claims: dict[str, Any]) -> None:
        self.discovery, self.claims = discovery, claims

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return self.discovery

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        body = base64.urlsafe_b64encode(json.dumps(self.claims).encode()).decode()
        return {"id_token": f"h.{body}.s"}


ISSUER = "https://id.example"
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/auth",
    "token_endpoint": f"{ISSUER}/token",
}
GOOD = {"iss": ISSUER, "aud": "cid", "sub": "1", "exp": time.time() + 60, "nonce": "n"}


@pytest.mark.parametrize(
    ("discovery", "claims"),
    [
        (DISCOVERY, GOOD | {"iss": GOOGLE}),
        (DISCOVERY, GOOD | {"aud": "another"}),
        (DISCOVERY, GOOD | {"aud": ["cid", "another"]}),
        (DISCOVERY, GOOD | {"exp": time.time() - 1}),
        (DISCOVERY, GOOD | {"nonce": "other"}),
        (DISCOVERY | {"issuer": GOOGLE}, GOOD),
        (DISCOVERY | {"token_endpoint": "http://id.example/token"}, GOOD),
    ],
)
async def test_the_issuer_checks(discovery, claims):
    issuer = Issuer(ISSUER, "cid", "secret", Answers(discovery, claims))
    with pytest.raises(LoginFailed):
        await issuer.identity("code", "https://app.example/cb", Flow("s", "n", "v"))


async def test_the_issuer_accepts_good_claims():
    issuer = Issuer(ISSUER, "cid", "secret", Answers(DISCOVERY, GOOD | {"email": "A@x.io"}))
    who = await issuer.identity("code", "https://app.example/cb", Flow("s", "n", "v"))
    assert (who.issuer, who.subject, who.email, who.email_verified) == (
        ISSUER,
        "1",
        "a@x.io",
        False,
    )
