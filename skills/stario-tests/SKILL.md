---
name: stario-tests
description: TestClient tests for a Stario app - pages, Datastar commands, plain forms, live streams in two tabs, sign-in, bad input. Use when the task asks for tests or ships no acceptance suite. Not when the task ships its own suite (npm test, Playwright).
---

# Tests with TestClient

The scaffold's `tests/conftest.py` has the fixture `client`: a `TestClient` on the real
bootstrap, with a fresh data folder per test. It runs the server protocol in memory: no port, no
server to stop. Write one file per page area, `tests/test_<area>.py`, and run
`uvx stario-create@latest check` (or `uv run pytest -q tests/test_<area>.py`).

Test what a user sees and does: the HTML of a page, the answer of a command, the next event of a
stream. Import routes from `app.urls`; never write a URL by hand.

```python
# tests/test_bookmarks.py
from stario.json import dumps

from app.urls import ADD_BOOKMARK, BOOKMARKS, BOOKMARKS_LIVE
from tests.test_pages import check


async def add(client, title: str, url: str = "https://example.com"):
    """A Datastar action: the JSON body is the signals."""
    return await client.post(ADD_BOOKMARK.href(), json={"title": title, "url": url})


async def test_an_added_bookmark_is_listed_and_found(client):
    await add(client, "Python docs")
    page = await client.get(BOOKMARKS.href(query={"q": "pyth"}))
    assert "Python docs" in page.text
    assert "Python docs" not in (await client.get(BOOKMARKS.href(query={"q": "rust"}))).text
    # The page check of tests/test_pages.py, on a page that has rows now.
    assert not await check(client, BOOKMARKS.href(query={"q": "pyth"}))


async def test_bad_input_shows_an_error_and_writes_nothing(client):
    r = await add(client, "", "ftp://x")
    assert "required" in r.text  # the patch_signals event of the answer
    assert "No bookmarks yet" in (await client.get(BOOKMARKS.href())).text


async def test_a_new_bookmark_reaches_every_tab(client):
    async with (
        client.stream("GET", BOOKMARKS_LIVE.href(), timeout=2) as one,
        client.stream("GET", BOOKMARKS_LIVE.href(), timeout=2) as two,
    ):
        tab1, tab2 = one.iter_events(), two.iter_events()
        await anext(tab1)  # the first event is the element as it is now
        await anext(tab2)
        await add(client, "Live one")
        assert "Live one" in (await anext(tab1))["data"]  # assert the next event
        assert "Live one" in (await anext(tab2))["data"]


async def test_signals_on_a_get(client):
    r = await client.get(BOOKMARKS.href(), params={"datastar": dumps({"q": "x"})})
    assert r.status_code == 200
```

`timeout=2` on a stream turns a missing event into a `TimeoutError` instead of a hung test.
An event is a dict: `event["event"]` (`datastar-patch-elements`, `datastar-patch-signals`) and
`event["data"]` (the HTML or the JSON).

## Calls

- `await client.get(url, params={...}, headers={...})`; `r.status_code`, `r.text`, `r.json()`,
  `r.headers.get("location")`.
- A plain form: `await client.post(url, data={"email": "a@b.co"}, follow_redirects=False)`, then
  check `r.status_code == 303` and the location. Redirects are followed unless you say so.
- Upload: `files={"photo": ("a.png", b"...", "image/png")}` next to `data=`.
- Cookies stay in `client.cookies` across calls: sign in once and the next calls are signed in.
  `client.cookies.clear()` signs out; to act as a second user, clear and sign in as them.
- A route behind `session.require` answers 303 to `/login?next=...` when signed out.
- Background work started with `c.app.create_task`: `await client.drain_tasks()` waits for it.

## Signed in

With `add auth --password`, sign up through the form, as `tests/test_login.py` does:

```python
# tests/test_notes_auth.py
from app.urls import SIGN_UP


async def sign_up(client, name: str = "ada") -> None:
    form = {"username": name, "email": f"{name}@example.com", "password": "correct horse"}
    r = await client.post(SIGN_UP.href(), data=form, follow_redirects=False)
    assert r.status_code == 303


async def test_a_signed_in_user_sees_the_page(client):
    await sign_up(client)
    assert (await client.get("/", follow_redirects=False)).status_code == 200
```

## What not to test

The framework, the kits' own files (their tests ship with them), and markup details nobody
relies on. Do not edit `tests/conftest.py` to start other servers; a page that calls an outside
service gets a fake client in its own test (skill `stario-outside-api`).
