---
name: stario-feature
description: A whole Stario page to copy - its SQLite table, reads and writes, the live view, a form command with an error message, its tests - plus navigate to a new page, and paging. Use when you add a page that keeps data, or a page does not refresh in other tabs. Sort, filter, search - stario-view. Memory or one-tab messages - stario-relay. Slow work - stario-jobs.
---

# A whole page

`AGENTS.md` holds the rules; `stario-api` and `stario-datastar` hold the names. Copy the four files below, rename, and write each feature in one step.

1. One folder `app/features/<page>/` with `__init__.py`, named after the URL noun: `/rooms/{room_id}` is `room`.
2. Rows in SQLite (`new --db`, or `uv add "litewriter>=0.3.3,<0.4"`): `db.watch`. In memory: `stario-relay`.
3. `app/main.py`: `todos_data.schema(tx)` in `schema`, `TodosPage(db).register(app)` under `# pages`. `(TODOS, "Todos")` in `LINKS` (home `views.py`).
4. Tests as AGENTS.md says, then `just check`.

## A live page

A shared todo list. The stream follows `db.watch`, so the commands only write.

```python
# urls.py
from stario import Route

TODOS = Route("GET /todos")
TODOS_LIVE = Route("GET /todos/live")
ADD_TODO = Route("POST /todos")
TOGGLE_TODO = Route("POST /todos/{todo_id}/toggle")
```

```python
# data.py
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
# views.py
from stario import h
from stario.datastar import at, data
from stario.markup import HtmlElement

from app.common.shell import page
from app.features.todos.data import Todo
from app.features.todos.urls import ADD_TODO, TODOS_LIVE, TOGGLE_TODO


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

```python
# handlers.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer
from stario.datastar import SSE, read_signals

from app.features.todos.data import ITEMS, Todo, add_todo, get_todo, list_todos, toggle_done
from app.features.todos.urls import ADD_TODO, TODOS, TODOS_LIVE, TOGGLE_TODO
from app.features.todos.views import render


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
```

`add` replies with `patch_signals` (the error, or a cleared input), then awaits the write. The commit wakes the watch, and every open tab repaints. A page that reads several tables watches one small query that changes with them, and reads the rest in the loop:

```python
async with self.db.watch(VERSION, article_id=article.id) as versions:
    async for _ in c.alive(versions):
        sse.patch_elements(render(get_article(self.db, article.id), viewer))
```

## Tests

```python
# tests/test_todos.py
from app.features.todos.urls import ADD_TODO, TODOS, TODOS_LIVE, TOGGLE_TODO


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

Read the first event, so the subscription is up. Send the command. Assert the next event. `timeout=2` fails a missing repaint in two seconds: the whole check for "the other tab never updates", with no browser.

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

## Paging

The page number is in the query: `TODOS.href(query={"page": 2})`, read with `c.req.query.get("page", "1")` (check `isdecimal()`). SQL: `LIMIT :limit OFFSET :offset`, and `count(*)` for the number of pages. Each page number is an `<a href>`. Sort and filter: skill `stario-view`.

## Remove a page, or split one

Delete its folder and test file, its `register` and `schema` lines, and fix the imports pyrefly reports. Ask before you drop its tables. A `handlers.py` over about 300 lines usually hides a second resource: split by URL noun, not by layer.
