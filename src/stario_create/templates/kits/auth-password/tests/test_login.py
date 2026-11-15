from app.auth.password import check_password, hash_password
from app.urls import LOGIN, LOGOUT, SIGN_IN, SIGN_UP

# The prefix that session.require protects in app/main.py. It has no page yet,
# so a signed-in request gets 404 and a signed-out one gets 303.
PROTECTED = "/app"
ADA = {"username": "ada", "email": "ada@example.com", "password": "correct horse"}


async def sign_up(client, **fields: str):
    return await client.post(SIGN_UP.href(), json=ADA | fields)


async def test_sign_up_signs_in_and_logout_signs_out(client):
    r = await sign_up(client, next="/app/x")
    assert "window.location" in r.text and "/app/x" in r.text
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 404
    await client.post(LOGOUT.href(), follow_redirects=False)
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 303


async def test_sign_in_checks_the_password(client):
    await sign_up(client)
    client.cookies.clear()
    r = await client.post(SIGN_IN.href(), json={"email": "ADA@example.com", "password": "nope"})
    assert "email or password is invalid" in r.text
    r = await client.post(SIGN_IN.href(), json={"email": "nobody@example.com", "password": "x"})
    assert "email or password is invalid" in r.text
    r = await client.post(
        SIGN_IN.href(), json={"email": "ADA@example.com", "password": ADA["password"]}
    )
    assert "window.location" in r.text
    assert (await client.get(PROTECTED, follow_redirects=False)).status_code == 404


async def test_a_taken_email_or_username_and_bad_input_are_refused(client):
    await sign_up(client)
    assert "taken" in (await sign_up(client, username="bob")).text
    assert "taken" in (await sign_up(client, email="bob@example.com", username="ADA")).text
    assert "8 or more" in (await sign_up(client, email="c@example.com", password="short")).text
    assert "required" in (await sign_up(client, email="no-at-sign")).text


async def test_a_protected_page_sends_a_visitor_to_login_and_back(client):
    r = await client.get(f"{PROTECTED}?tab=2", follow_redirects=False)
    assert r.headers.get("location") == f"{LOGIN.href()}?next=%2Fapp%3Ftab%3D2"
    r = await client.get(PROTECTED, headers={"datastar-request": "true"})
    assert "window.location" in r.text
    assert 'id="login"' in (await client.get(LOGIN.href())).text


async def test_an_outside_next_goes_home(client):
    r = await sign_up(client, next="//evil.example")
    assert "//evil.example" not in r.text


def test_a_hash_checks_only_its_password():
    stored = hash_password("secret")
    assert check_password("secret", stored)
    assert not check_password("Secret", stored)
    assert not check_password("secret", "garbage")
