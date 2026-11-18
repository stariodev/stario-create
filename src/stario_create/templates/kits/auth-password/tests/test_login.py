"""The sign-in kit by behaviour: sessions, refusals, redirects. No test reads a label or
an error text, so the pages may change their paths, wording and markup freely."""

from app.auth.password import check_password, hash_password
from app.urls import LOGIN, LOGOUT, SIGN_IN, SIGN_UP

# The prefix that session.require protects in app/main.py. It has no page yet,
# so a signed-in request gets 404 and a signed-out one gets 303.
PROTECTED = "/app"
ADA = {"username": "ada", "email": "ada@example.com", "password": "correct horse"}


async def sign_up(client, **fields: str):
    return await client.post(SIGN_UP.href(), data=ADA | fields, follow_redirects=False)


async def sign_in(client, email: str, password: str):
    form = {"email": email, "password": password}
    return await client.post(SIGN_IN.href(), data=form, follow_redirects=False)


async def signed_in(client) -> bool:
    return (await client.get(PROTECTED, follow_redirects=False)).status_code == 404


async def test_sign_up_signs_in_and_logout_signs_out(client):
    r = await sign_up(client, next="/app/x")
    assert (r.status_code, r.headers.get("location")) == (303, "/app/x")
    assert await signed_in(client)
    r = await client.post(LOGOUT.href(), follow_redirects=False)
    assert r.status_code == 303
    assert not await signed_in(client)


async def test_sign_in_checks_the_password(client):
    await sign_up(client)
    client.cookies.clear()
    assert (await sign_in(client, "ADA@example.com", "nope")).status_code == 422
    assert (await sign_in(client, "nobody@example.com", "x")).status_code == 422
    assert not await signed_in(client)
    r = await sign_in(client, "ADA@example.com", ADA["password"])
    assert r.status_code == 303
    assert await signed_in(client)


async def test_a_taken_email_or_username_and_bad_input_are_refused(client):
    await sign_up(client)
    client.cookies.clear()
    refused = [
        {"username": "bob"},
        {"email": "bob@example.com", "username": "ADA"},
        {"email": "c@example.com", "username": "c", "password": "short"},
        {"email": "no-at-sign", "username": "d"},
        {"email": "e@example.com", "username": ""},
    ]
    for fields in refused:
        r = await sign_up(client, **fields)
        assert r.status_code == 422, fields
        assert 'name="email"' in r.text, fields
    assert not await signed_in(client)


async def test_a_protected_page_sends_a_visitor_to_login_and_back(client):
    r = await client.get(f"{PROTECTED}?tab=2", follow_redirects=False)
    assert r.headers.get("location") == f"{LOGIN.href()}?next=%2Fapp%3Ftab%3D2"
    r = await client.get(PROTECTED, headers={"datastar-request": "true"})
    assert "window.location" in r.text
    page = await client.get(LOGIN.href(query={"next": "/app?tab=2"}))
    assert 'value="/app?tab=2"' in page.text


async def test_an_outside_next_goes_home(client):
    r = await sign_up(client, next="//evil.example")
    assert r.headers.get("location") == "/"


def test_a_hash_checks_only_its_password():
    stored = hash_password("secret")
    assert check_password("secret", stored)
    assert not check_password("Secret", stored)
    assert not check_password("secret", "garbage")
