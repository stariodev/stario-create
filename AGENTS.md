# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia. A handler writes HTML. Datastar morphs it into the page. One open SSE response keeps a page live. State lives on the server. Not ASGI: no Uvicorn, FastAPI, Jinja, or response objects.

This file holds the rules and the shape of a page. Two skills hold every signature: `stario-api` (server: the port, a 404 page, redirects, errors, cookies, forms, static files, SQLite, tests) and `stario-datastar` (page: `h.*`, `data.*`, `at.*`, `SSE`). Read both once before you write code. Never read the stario source in site-packages: what they do not list, pyrefly checks.

The last section of this file holds the notes of this app, under 4 KB. A deep note on one topic goes in its own file, named by a line such as "Read `EDITOR.md` first."

## Start an app

```bash
uvx stario-create@latest new app --db   # the folder: `app`, `.`, any path; --db adds SQLite
```

Run it where the app should live. It installs the dependencies, writes a tested app, runs its tests, and prints what each file holds. `app/main.py` holds `bootstrap(app, span)`: it opens `LiteWriter(config.db_path, schema=schema)` as `db` (`schema` is in `app/data.py`) and registers each page under `# pages`: `TodosPage(db).register(app)`. Without `--db` there is no `LiteWriter` and no `app/data.py`.

Run the app with `just dev` (reloads) or `just serve`, on `STARIO_HOST:STARIO_PORT` (default `127.0.0.1:8000`): `STARIO_PORT=4000 uv run python -m app.main`. Yard sets `STARIO_HOST`, `STARIO_PORT`, and `PROJECT_DATA_DIR`.

## Layout

```text
app/main.py         bootstrap: shared objects, one register line per page
app/config.py       Config: one field with a default per setting; from_env reads FIELD_NAME
app/layout.py       ASSETS, page(title, body): the <html> document, and markup pages share
app/urls.py         every Route, grouped under a comment per page
app/data.py         schema(tx), the row dataclasses, every read and write (SQL)
app/pages/<page>.py one page: its class (the handlers), then its render functions
app/<name>.py       code with no URL (an API client, a parser); never imports pages
static/             css/ and js/: ASSETS.href("css/app.css")
tests/test_<page>.py  tests/conftest.py has `client`; keep test_pages.py and test_js.py
```

- A page is one file named after the URL noun: `/rooms/{room_id}` is `app/pages/room.py`, with one line in `LINKS` in `app/pages/home.py`. It imports `app.urls`, `app.data`, and `app.layout`, never another page.
- A file past about 400 lines splits by noun: `app/data.py` becomes `app/data/<noun>.py`.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string (skill `stario-client`).

## Rules

- `bootstrap(app, span)` is an async generator with one `yield`. Keep `app.use("/", same_origin(), security_headers())`. `same_origin()` is the CSRF guard: add no CSRF tokens. It does not check GET, so a GET never changes state.
- A handler is `async def (c: Context, w: Writer) -> None`. It answers once: `w.html`, `w.text`, `w.json`, `w.empty`, `w.redirect`, or `SSE(w)`.
- `Route("GET /rooms/{room_id}")` is one method on one path; a GET route answers HEAD too. `ROUTE.href(room_id, query={...})` builds the URL. No `url_for`.
- `c.match.params` values are strings: check, then convert. `c.req.query.get("page", "1")`.
- In `h.*`, attributes come first, children after: `h.A({"href": url}, classes("btn", {"on": on}), data.show("$x"), "text")`. A dict, `classes(...)`, and each `data.*` are attributes; `classes` never goes inside the dict. A dict after a child raises "HTML attributes must be passed before children" when the `h.*` call runs.
- A bare number in `debounce=`, `delay=`, or `throttle=` is seconds: write `debounce="300ms"`.
- A stream loop iterates `c.alive(source)`. Background work is `c.app.create_task(coro)`. A timer loop waits on `app.shutdown`, never `asyncio.sleep`.
- No module-level state. No `os.environ` outside `config.py`. JSON goes through `stario.json`.
- A middleware with a dependency is a method of a class built in `bootstrap`: `app.use("/", session.attach)`. Handlers read its state through a typed function such as `current_user(c)`, not `c.state[...]`.

## A page is a resource

- **Go somewhere** (a page, a sort, a filter, a page number): `<a href>`. The query holds the view.
- **A result only this tab needs** (search as you type): a `GET` that answers `SSE(w).patch_elements(part)`.
- **Change state**: a command, `POST`.

A page on state that cannot change while it is open is static: `w.html(render(...))`. A page on shared state is live:

```text
GET  /board        the document; its top element has data.init(at.get(BOARD_LIVE.href(), retry="always"))
GET  /board/live   the stream: send render(...), and again after each change
POST /board/...    a command
```

The stream is the only thing that sends the page's HTML. It follows `db.watch(query)` (SQLite) or `relay.subscribe(...)` (memory). A command never answers with the page:

1. Read: `await read_signals(c.req)` (a Datastar action), `c.match.params`. A plain HTML form or an upload: `await read_form(c.req)`.
2. Validate: bad input gets `SSE(w).patch_signals({"_error": "why"})` for the form to show, or `w.text("why", status=400)`, and `return`.
3. Reply: `w.empty()`, `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)`. Only the command navigates: a stream whose row is gone just returns.
4. Execute: `await db.write(...)`, or change memory, then `relay.publish(...)`.

## A page in code

`app/urls.py` gets `TODOS`, `TODOS_LIVE`, and `ADD_TODO`; `app/data.py` the table (skill `stario-feature`). `app/pages/todos.py`:

```python
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import ITEMS, Todo, add_todo, list_todos
from app.layout import page
from app.urls import ADD_TODO, TODOS, TODOS_LIVE


@dataclass(frozen=True, slots=True)
class TodosPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(TODOS, self.show)
        app.add(TODOS_LIVE, self.live)
        app.add(ADD_TODO, self.add)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(list_todos(self.db)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(ITEMS, Todo) as rows:
            async for todos in c.alive(rows):
                sse.patch_elements(render(todos))

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not title:
            SSE(w).patch_signals({"_error": "title can't be blank"})
            return
        SSE(w).patch_signals({"title": "", "_error": ""})
        await self.db.write(add_todo, title)


def render(todos: list[Todo]) -> HtmlElement:
    return page(
        "Todos",
        h.Main(
            {"id": "todos"},
            data.signals({"title": "", "_error": ""}, if_missing=True),
            data.init(at.get(TODOS_LIVE.href(), retry="always")),
            h.Form(
                data.on("submit", at.post(ADD_TODO.href()), prevent=True),
                h.Input({"name": "title"}, data.bind("title")),
                h.Button({"type": "submit"}, "Add"),
            ),
            h.P({"class": "error"}, data.show("$_error"), data.text("$_error")),
            h.Ul(*[h.Li(t.title) for t in todos]),
        ),
    )
```

- `render(...)` returns the whole document from state. It does not fetch. The element with `data.init` and `data.signals(..., if_missing=True)` keeps its tag, `id`, and attributes in every render.
- Signals carry what the user types. A leading `_` keeps a signal in the tab: the server can set it, the browser never sends it.
- A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.
- A page with several tables: watch one small query that changes when the page should (`SELECT count(*), max(id) FROM comments WHERE article_id = :id`), and read the rest inside the loop.

The page class's fields are its dependencies. A read or a write is a function in `app/data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`. No service classes, repositories, base pages, or `utils`.

## Write in few steps

Plan the routes, tables, and shared markup. Then write `app/urls.py`, `app/data.py`, `app/layout.py`, and the pages in one or two steps: one command (a chain of heredocs, or several writes in one message) can create ten files. Change the scaffold's files in place; do not delete and rewrite them. Write each file once: do not reopen, tidy, rename, or reword a file you just wrote. Fix only what `just check`, the tests, or the acceptance suite report (`just check` sorts and drops imports, but does not move one below code). No `__all__`. A wrong name costs a rewrite: look it up in the skills before you write it.

## Change an existing app

An app keeps the layout it has. `grep -rn 'Route("' app` lists every URL and its file; the page is named by its noun. Read that page, `app/urls.py`, and the part of `app/data.py` it uses, not the whole app. An older app has a folder per page (`app/features/<page>/`: `urls.py`, `views.py`, `handlers.py`, `data.py`): add to it in that shape.

- A new URL: a `Route` in `app/urls.py`, a method on the page class, one line in its `register`.
- A database that already holds rows: `schema` runs at every start, so each change checks first (`IF NOT EXISTS`, a column missing from `pragma_table_xinfo`) and sets the old rows in that same step. Never drop or recreate a table that holds rows (skill `stario-litewriter`).
- A new live part on one page: widen the query its stream watches. A count on every page (a navbar badge): its own small stream (skill `stario-feature`).
- Run the existing tests and the acceptance suite before and after.

## Tests

`tests/conftest.py` gives `client`, a `TestClient(bootstrap)` on an empty data dir. A `GET` sends signals in `params={"datastar": '{"q": "x"}'}`, a Datastar `POST` in `json={...}`, a plain form in `data={...}`. The next SSE event of `client.stream(...)` is the changed HTML; two streams are two tabs. `tests/test_pages.py` checks every page by itself.

Test what nothing else checks. When the task comes with acceptance tests (an end-to-end suite such as `npm test`), that suite is the check: write no TestClient tests for what it covers, run it after each change, and stop when it passes. Without such a suite, each page gets one test file: it loads, a command repaints the stream, bad input is refused. A bug starts with a test that shows it.

## Checks

Change a file with the Edit tool. Run Python as `uv run python`. Run `just check` before you finish and after a failure: it formats, fixes lint, checks types, runs the tests, and prints only problems. pyrefly checks each call, so trust Stario, Datastar, and litewriter. Run a long test suite in the foreground and wait for it; do not poll a background run.

A browser is only for client JS that holds state. No computer use. When the user watches the app, the user is the browser: say what to look at. When it does not work: `curl` their server, then a failing test (skill `stario-browser-check`).

## Which skill

A page with SQLite, a form, a live list: `stario-feature`. Accounts and passwords: `stario-auth`. Sort, filter, search: `stario-view`. State in memory, an edit dialog: `stario-relay`. A new column on a table with rows: `stario-litewriter`. Slow work, a timer: `stario-jobs`. JavaScript: `stario-client`. Tailwind: `stario-tailwind-daisyui`. Before a browser: `stario-browser-check`.

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

## This app

Notes for this app go below. `stario-create sync` replaces the text above and keeps this section.
