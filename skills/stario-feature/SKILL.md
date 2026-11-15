---
name: stario-feature
description: Tests for a Stario page (stream, two tabs, bad input) and page extras - go to the page a command made, a navbar count, several tables, removing a page. Use when writing TestClient tests or one of these. Not for a first page.
---

# Tests for a page, and page extras

The first page is the todos page of AGENTS.md; this skill builds on its names (`TODOS`, `TODOS_LIVE`, `ADD_TODO`). When the task ships an acceptance suite, that suite is the check: write none of these tests.

## Tests for a page

One file per page: it loads, a command repaints every tab, bad input is refused.

```python
# tests/test_todos.py
from app.urls import ADD_TODO, TODOS, TODOS_LIVE
from tests.test_pages import check


async def test_add_shows_on_every_tab(client):
    async with (
        client.stream("GET", TODOS_LIVE.href(), timeout=2) as first,
        client.stream("GET", TODOS_LIVE.href(), timeout=2) as second,
    ):
        one, two = first.iter_events(), second.iter_events()
        assert 'id="todos"' in (await anext(one))["data"]
        assert 'id="todos"' in (await anext(two))["data"]
        r = await client.post(ADD_TODO.href(), json={"title": "milk"})
        assert r.status_code == 200
        assert "milk" in (await anext(one))["data"]
        assert "milk" in (await anext(two))["data"]


async def test_the_page_loads_with_rows_and_bad_input_is_refused(client):
    await client.post(ADD_TODO.href(), json={"title": "milk"})
    assert "milk" in (await client.get(TODOS.href())).text
    assert not await check(client, TODOS.href())  # the page check, with a row on the page
    assert "_error" in (await client.post(ADD_TODO.href(), json={"title": " "})).text
```

Read the first event (the subscription is up), send the command, assert the next event. `timeout=2` fails a missing repaint in two seconds, with no browser. A plain form posts `data={...}`; a GET with signals sends `params={"datastar": '{"q": "x"}'}`. Every `TestClient` call: skill `stario-api`, `references/testclient.md`.

## Go to the page a command made

The command writes first, because the URL needs the new id, then answers `navigate` (a test asserts `"window.location" in r.text`):

```python
async def create(self, c: Context, w: Writer) -> None:
    name = str((await read_signals(c.req)).get("name", "")).strip()
    if not 1 <= len(name) <= 80:
        SSE(w).patch_signals({"_error": "name must be 1 to 80 characters"})
        return
    room_id = await self.db.write(add_room, name)
    SSE(w).navigate(ROOM.href(room_id))
```

## A page on several tables

The stream watches one small query that changes when the page should, and reads the rest in the loop:

```python
async def live(self, c: Context, w: Writer) -> None:
    article_id, sse = int(c.match.params["article_id"]), SSE(w)
    version = "SELECT count(*), max(id) FROM comments WHERE article_id = :id"
    async with self.db.watch(version, id=article_id) as rows:
        async for _ in c.alive(rows):
            article = get_article(self.db, article_id)
            if article is None:
                return
            sse.patch_elements(render(article, list_comments(self.db, article_id)))
```

## A live count on every page

A navbar count (unread notifications) has its own stream of one signal. The element skips the page's morphs:

```python
h.Span(  # in the navbar in app/layout.py
    {"id": "unread"},
    data.signals({"_unread": 0}, if_missing=True),
    data.init(at.get(UNREAD_LIVE.href(), retry="always")),
    data.ignore_morph(),
    data.text("$_unread"),
)


async def unread(self, c: Context, w: Writer) -> None:  # UNREAD_LIVE, behind session.require
    sse = SSE(w)
    async with self.db.watch(UNREAD, user_id=signed_in_user(c)) as rows:
        async for counts in c.alive(rows):
            sse.patch_signals({"_unread": counts[0][0]})
```

## Remove a page, or split one

Delete its file, test, routes, and `register` line; pyrefly reports the imports left behind. Ask before you drop its tables. A page file over 400 lines hides a second resource: split it by URL noun.
