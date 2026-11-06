from stario.testing import TestClient

from app.features.login.urls import LOGIN, LOGIN_CALLBACK, LOGOUT
from app.main import bootstrap
from tests.conftest import login, start

# The prefix that session.require protects in app/main.py.
PROTECTED = "/app"


async def test_a_protected_page_sends_a_visitor_to_login_and_back(client):
    r = await client.get(PROTECTED, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == f"{LOGIN.href()}?next=%2Fapp"
    r = await client.get(PROTECTED, headers={"datastar-request": "true"})
    assert "window.location" in r.text
    r = await login(client, next_url=PROTECTED)
    assert r.headers.get("location") == PROTECTED


async def test_the_start_sends_state_nonce_and_pkce(client):
    query = await start(client)
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"].endswith(LOGIN_CALLBACK.href())
    assert query["state"] and query["nonce"]


async def test_login_then_logout(client):
    assert (await login(client)).headers.get("location") == "/"
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code != 303
    await client.post(LOGOUT.href(), follow_redirects=False)
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_a_callback_without_the_start_signs_nobody_in(client):
    r = await client.get(
        LOGIN_CALLBACK.href(),
        params={"code": "ada@example.com x", "state": "forged"},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "expired"})
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_a_wrong_nonce_fails(client):
    query = await start(client)
    r = await client.get(
        LOGIN_CALLBACK.href(),
        params={"code": "ada@example.com another-nonce", "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})


async def test_a_cancel_at_the_issuer_says_so(client):
    query = await start(client)
    r = await client.get(
        LOGIN_CALLBACK.href(),
        params={"error": "access_denied", "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "denied"})
    assert "cancelled" in (await client.get(str(r.headers.get("location")))).text


async def test_an_outside_next_goes_home(client):
    r = await login(client, next_url="//evil.example")
    assert r.headers.get("location") == "/"


async def test_the_allow_list_keeps_other_accounts_out(env):
    env.setenv("LOGIN_ALLOWED_EMAILS", "ada@example.com")
    async with TestClient(bootstrap, request_timeout=5) as client:
        r = await login(client, email="bob@example.com")
        assert r.headers.get("location") == LOGIN.href(query={"error": "not_allowed"})
        assert (await login(client)).headers.get("location") == "/"
