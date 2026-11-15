---
name: stario-feature
description: A whole Stario page to copy - its SQLite table, reads and writes, live view, form command with an error, tests; navigate after create; paging. Use to add a page that keeps data.
---

# A whole page

`AGENTS.md` holds the rules; `stario-api` and `stario-datastar` hold the names. Copy the three parts below, rename, and write them in one step.

1. Routes in `app/urls.py`, under a comment with the page name.
2. Rows in SQLite (`new --db`, or `uv add "litewriter>=0.3.3,<0.4"` and an `app/data.py`): the table, its row dataclass, its reads and writes in `app/data.py`, and its `CREATE TABLE` in `schema`. In memory: `stario-relay`.
3. The page in `app/pages/<page>.py`, named after the URL noun: `/rooms/{room_id}` is `room.py`. `app/main.py`: `TodosPage(db).register(app)` under `# pages`. `(TODOS, "Todos")` in `LINKS` in `app/pages/home.py`.
4. Tests as AGENTS.md says, then `just check`.

## A live page

A shared todo list. The stream follows `db.watch`, so the commands only write.

```python
# app/urls.py
# todos
TODOS = Route("GET /todos")
TODOS_LIVE = Route("GET /todos/live")
ADD_TODO = Route("POST /todos")
TOGGLE_TODO = Route("POST /todos/{todo_id}/toggle")
```

```python
# app/data.py
from dataclasses import dataclass

from litewriter import LiteWriter, Tx
from stario.json import dumps

COLUMNS = {
    "title": "TEXT AS (data->>'title')",
    "done": "INTEGER AS (data->>'done')",
}

ITEMS = "SELECT id, title, done FROM todos ORDER BY id"


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    title: str
    done: int


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS todos ("
        " id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
    )
    have = {row[0] for row in tx.query("SELECT name FROM pragma_table_xinfo('todos')")}
    for name, column in COLUMNS.items():
        if name not in have:
            tx.execute(f"ALTER TABLE todos ADD COLUMN {name} {column} VIRTUAL")


def list_todos(db: LiteWriter) -> list[Todo]:
    return db.query(ITEMS, Todo)


def get_todo(db: LiteWriter, todo_id: int) -> Todo | None:
    return db.one("SELECT id, title, done FROM todos WHERE id = :id", Todo, id=todo_id)


def add_todo(tx: Tx, title: str) -> int:
    return tx.value(
        "INSERT INTO todos (data) VALUES (:data) RETURNING id",
        data=dumps({"title": title, "done": False}),
    )


def toggle_done(tx: Tx, todo_id: int) -> None:
    tx.execute(
        "UPDATE todos SET data = json_set(data, '$.done', json(iif(done, 'false', 'true')))"
        " WHERE id = :id",
        id=todo_id,
    )
```

```python
# app/pages/todos.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import ITEMS, Todo, add_todo, get_todo, list_todos, toggle_done
from app.layout import page
from app.urls import ADD_TODO, TODOS, TODOS_LIVE, TOGGLE_TODO


@dataclass(frozen=True, slots=True)
class TodosPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(TODOS, self.show)
        app.add(TODOS_LIVE, self.live)
        app.add(ADD_TODO, self.add)
        app.add(TOGGLE_TODO, self.toggle)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(list_todos(self.db)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(ITEMS, Todo) as rows:
            async for todos in c.alive(rows):
                sse.patch_elements(render(todos))

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not title or len(title) > 200:
            SSE(w).patch_signals({"_error": "title must be 1 to 200 characters"})
            return
        SSE(w).patch_signals({"title": "", "_error": ""})
        await self.db.write(add_todo, title)

    async def toggle(self, c: Context, w: Writer) -> None:
        todo_id = c.match.params["todo_id"]
        if not todo_id.isdecimal() or get_todo(self.db, int(todo_id)) is None:
            w.text("no such todo", status=404)
            return
        w.empty()
        await self.db.write(toggle_done, int(todo_id))


def render(items: list[Todo]) -> HtmlElement:
    return page(
        "Todos",
        h.Main(
            {"id": "todos"},
            data.signals({"title": "", "_error": ""}, if_missing=True),
            data.init(at.get(TODOS_LIVE.href(), retry="always")),
            h.Form(
                data.on("submit", at.post(ADD_TODO.href()), prevent=True),
                data.indicator("_adding"),
                h.Input({"type": "text", "maxlength": 200}, data.bind("title")),
                h.Button({"type": "submit"}, data.attr("disabled", "$_adding"), "Add"),
            ),
            h.Ul({"class": "error-messages"}, data.show("$_error"), h.Li(data.text("$_error"))),
            h.Ul(*[item(t) for t in items]) if items else h.P("No todos yet."),
        ),
    )


def item(t: Todo) -> HtmlElement:
    return h.Li(
        h.Label(
            h.Input(
                {"type": "checkbox", "checked": bool(t.done)},
                data.on("click", at.post(TOGGLE_TODO.href(t.id)), prevent=True),
            ),
            h.S(t.title) if t.done else t.title,
        )
    )
```

`add` replies with `patch_signals` (the error, or a cleared input), then awaits the write. The commit wakes the watch, and every open tab repaints. A page on several tables watches one small query (`SELECT count(*), max(id) FROM comments WHERE article_id = :id`) and reads the rest in the loop.

## Tests

```python
# tests/test_todos.py
from app.urls import ADD_TODO, TODOS, TODOS_LIVE, TOGGLE_TODO


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


async def test_toggle_repaints_the_stream(client):
    await client.post(ADD_TODO.href(), json={"title": "milk"})
    async with client.stream("GET", TODOS_LIVE.href(), timeout=2) as live:
        events = live.iter_events()
        assert "checked" not in (await anext(events))["data"]
        assert (await client.post(TOGGLE_TODO.href(1))).status_code == 204
        assert "checked" in (await anext(events))["data"]


async def test_the_page_loads_and_bad_input_is_refused(client):
    assert 'id="todos"' in (await client.get(TODOS.href())).text
    assert "_error" in (await client.post(ADD_TODO.href(), json={"title": " "})).text
    assert (await client.post(TOGGLE_TODO.href(99))).status_code == 404
```

Read the first event (the subscription is up), send the command, assert the next event. `timeout=2` fails a missing repaint in two seconds, with no browser.

## Go to the page a command made

A command that creates a page of its own writes first, because the URL needs the new id, then answers `navigate` (a test asserts `"window.location" in r.text`):

```python
async def create(self, c: Context, w: Writer) -> None:
    name = str((await read_signals(c.req)).get("name", "")).strip()
    if not name or len(name) > 80:
        SSE(w).patch_signals({"_error": "name must be 1 to 80 characters"})
        return
    room_id = await self.db.write(add_room, name)
    SSE(w).navigate(ROOM.href(room_id))
```

## A live count on every page

A navbar count (unread notifications) has its own stream. The element skips the page's morphs and shows a signal that its stream sends:

```python
h.Span(  # in the navbar in app/layout.py
    {"id": "unread"},
    data.signals({"_unread": 0}, if_missing=True),
    data.init(at.get(UNREAD_LIVE.href(), retry="always")),
    data.ignore_morph(),
    data.text("$_unread"),
)


async def unread(self, c: Context, w: Writer) -> None:  # UNREAD_LIVE
    sse = SSE(w)
    async with self.db.watch(UNREAD, user_id=require_user(c)) as rows:
        async for rows in c.alive(rows):
            sse.patch_signals({"_unread": rows[0][0]})
```

## Paging

`TODOS.href(query={"page": 2})`, read with `c.req.query.get("page", "1")` (check `isdecimal()`). SQL: `LIMIT :limit OFFSET :offset`, and `count(*)` for the pages. Each page number is an `<a href>`.

## Remove a page, or split one

Delete its file, test, routes, and `register` line; pyrefly reports the imports. Ask before you drop its tables. A page file over 400 lines hides a second resource: split by URL noun.
