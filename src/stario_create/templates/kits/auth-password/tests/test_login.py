from app.features.login.urls import LOGIN, LOGOUT
from tests.conftest import login

# The prefix that session.require protects in app/main.py.
PROTECTED = "/app"


async def test_a_protected_page_sends_a_visitor_to_login(client):
    r = await client.get(PROTECTED, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == f"{LOGIN.href()}?next=%2Fapp"
    r = await client.get(PROTECTED, headers={"datastar-request": "true"})
    assert "window.location" in r.text


async def test_login_then_logout(client):
    assert "window.location" in await login(client)
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code != 303
    await client.post(LOGOUT.href())
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_a_wrong_password_and_an_unknown_email_get_one_answer(client):
    wrong = await login(client, password="not-the-password")
    unknown = await login(client, email="eve@example.com")
    assert "Wrong email or password" in wrong
    assert "Wrong email or password" in unknown
    assert "window.location" not in wrong + unknown


async def test_five_wrong_passwords_lock_the_account(client):
    for _ in range(5):
        await login(client, password="not-the-password")
    assert "Too many tries" in await login(client)


async def test_there_is_no_sign_up(client):
    assert (await client.get("/signup")).status_code == 404
