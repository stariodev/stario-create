<!-- BEGIN stario-create -->
# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia: a handler writes HTML, Datastar morphs it into the page, and one open SSE response keeps a page live. Not ASGI: no Uvicorn, FastAPI, or Jinja. This file is enough for a working app; the table at the end names the skill for each feature.

## The loop

1. `uvx stario-create@latest new app --db` where the app lives (`app`, `.`, any path). It installs, writes a tested app, and prints the files you will edit, so you need not open them.
2. Write every file in one message: several Write calls, or one command with a heredoc per file (`cat > app/urls.py <<'EOF' ... EOF`, then the next). Leave imports and their order to the check; do not reopen or tidy a file you just wrote. `uvx stario-create@latest add page NAME...` writes a page file with its route, register line, and home link.
3. `just check` (without `just`: `uvx stario-create@latest check`) formats, fixes lint, runs pyrefly, the tests, and the Stario lint, and prints only problems, each with its fix. Fix what it says; never read `site-packages`.
4. When the task ships an acceptance suite (`npm test`, Playwright), that suite is the check: run it after `just check`, and stop when both pass. Write no tests of your own for it.
5. See a page without a server: `uvx stario-create@latest request GET /todos` prints the HTML or the first stream events (`POST /todos -j '{"title": "x"}'` sends a Datastar action). Stop a server you started with `kill $!`, never `pkill -f` (it stops other apps). Wrap no command in `timeout`: macOS has none.

`just serve` (`just dev` reloads) listens on `STARIO_HOST:STARIO_PORT`, default `127.0.0.1:8000`. A platform that gives `$PORT`: `STARIO_HOST=0.0.0.0 STARIO_PORT=$PORT uv run python -m app.main`. A setting is a field with a default in `Config` (`app/config.py`); `from_env` reads its name in capitals. A spec's `DATABASE_PATH` is a field `database_path: Path = Path("data/app.sqlite3")`, opened in place of `db_path`.

## Imports

```python
from stario import App, Context, RedirectException, Relay, Route, Writer, classes, h
from stario.datastar import SSE, at, data, read_signals  # not from `stario`
from stario.datastar.format import string_literal  # user text inside an expression
from stario.forms import read_form
from stario.json import dumps, loads  # loads returns object: cast(list[str], loads(s))
from stario.markup import HtmlElement
from litewriter import LiteWriter, Tx
import apsw  # apsw.ConstraintError: a UNIQUE or CHECK failed
```

## A live page

A page on shared state has three routes. The stream is the only thing that sends the page's HTML; it follows `db.watch(sql)`, so a command only validates, writes, and replies.

```python
# app/urls.py
from stario import Route

TODOS = Route("GET /todos")
TODOS_LIVE = Route("GET /todos/live")
ADD_TODO = Route("POST /todos")
```

```python
# app/data.py
from dataclasses import dataclass

from litewriter import LiteWriter, Tx

PAGE_SIZE = 10
TODOS_PAGE = "SELECT id, title FROM todos ORDER BY id DESC LIMIT :limit OFFSET :offset"


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    title: str


def schema(tx: Tx) -> None:  # runs at every start: IF NOT EXISTS on every CREATE
    tx.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")


def list_todos(db: LiteWriter, page: int) -> list[Todo]:
    return db.query(TODOS_PAGE, Todo, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)


def add_todo(tx: Tx, title: str) -> int:
    return tx.value("INSERT INTO todos (title) VALUES (:title) RETURNING id", title=title)
```

```python
# app/pages/todos.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import PAGE_SIZE, TODOS_PAGE, Todo, add_todo, list_todos
from app.layout import page
from app.urls import ADD_TODO, TODOS, TODOS_LIVE


def page_number(c: Context) -> int:
    raw = c.req.query.get("page", "1")
    return int(raw) if raw.isdecimal() and int(raw) > 0 else 1


@dataclass(frozen=True, slots=True)
class TodosPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(TODOS, self.show)
        app.add(TODOS_LIVE, self.live)
        app.add(ADD_TODO, self.add)

    async def show(self, c: Context, w: Writer) -> None:
        n = page_number(c)
        w.html(render(list_todos(self.db, n), n))

    async def live(self, c: Context, w: Writer) -> None:
        n, sse = page_number(c), SSE(w)
        offset = (n - 1) * PAGE_SIZE
        async with self.db.watch(TODOS_PAGE, Todo, limit=PAGE_SIZE, offset=offset) as rows:
            async for todos in c.alive(rows):
                sse.patch_elements(render(todos, n))

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not 1 <= len(title) <= 200:
            SSE(w).patch_signals({"_error": "title must be 1 to 200 characters"})
            return
        await self.db.write(add_todo, title)
        SSE(w).patch_signals({"title": "", "_error": ""})


def render(todos: list[Todo], n: int) -> HtmlElement:
    return page(
        "Todos",
        h.Main(
            {"id": "todos"},
            data.signals({"title": "", "_error": ""}, if_missing=True),
            data.init(at.get(TODOS_LIVE.href(query={"page": n}), retry="always")),
            h.Form(
                data.on("submit", at.post(ADD_TODO.href()), prevent=True),
                h.Input({"name": "title", "maxlength": 200}, data.bind("title")),
                h.Button({"type": "submit"}, "Add"),
            ),
            h.P({"class": "error"}, data.show("$_error"), data.text("$_error")),
            h.Ul(*[h.Li(t.title) for t in todos]),
            h.A({"href": TODOS.href(query={"page": n + 1})}, "Older"),
        ),
    )
```

`app/main.py` registers it under `# pages`: `TodosPage(db).register(app)`; `app/pages/home.py` links it with `(TODOS, "Todos")` in `LINKS`.

- `render` returns the whole document from its arguments. The element with `data.init` and `data.signals(..., if_missing=True)` keeps its tag, `id`, and attributes in every render, so what the user typed survives each repaint.
- A signal with a leading `_` stays in the tab: the server can set it, the browser never sends it.
- A page on state that cannot change while it is open is static: `show` only, no stream.

## Commands

1. Read: `await read_signals(c.req)` (a dict); `c.match.params["id"]` (a string: check, then convert). A plain `<form method="post">` or an upload: `with await read_form(c.req) as f: f.get("title", "")`.
2. Validate: a bad value gets `SSE(w).patch_signals({"_error": "why"})`, a missing row `w.text("not found", status=404)`, then `return`. A taken unique value: catch `apsw.ConstraintError` around `await self.db.write(...)` and patch `_error`.
3. Write: `await self.db.write(fn, *args)`; `fn(tx, ...)` lives in `app/data.py` and holds no network call and no password hash. State in memory: skill `stario-relay`.
4. Reply once: `w.empty()`, `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)`. A plain form answers `w.redirect(url, status=303)`. Only a command navigates: a stream whose row is gone just returns.

A GET never changes state. A view (sort, filter, page number) is the URL query, reached by `<a href>`; search as you type is a `GET` that patches one part (skill `stario-view`).

## Names

```text
w.html(node, status=200)  w.text(s, status=400)  w.json(v)  w.empty()  w.redirect(url, status=303)
SSE(w).patch_elements(node)  .patch_signals({...})  .navigate(url)
ROUTE.href(7, query={"page": 2})   Route("GET /docs/{path...}")   app.not_found("/", handler)
c.req.query.get(k, default)  c.req.cookies.get(k)  c.alive(source)  c.app.create_task(coro)
db.query(sql, Row, **p) -> list   db.one(...) -> Row | None   db.value(sql, **p)   await db.write(fn, *a)
data.on("click", expr, prevent=True, debounce="300ms")  # a bare number is seconds
data.attr("disabled", "$_saving")  data.indicator("_saving")  data.class_("on", expr)
data.ref("_dialog")  data.preserve_attr("open")  data.ignore_morph()  at.delete(url)
```

`h.Div`, `h.A`, `h.HtmlDocument`: attributes first (a dict, `classes("btn", {"on": on})`, each `data.*`), then children. `classes` never goes inside the dict. `True` writes a bare attribute; `None` leaves it out. A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.

## Rules

- `bootstrap(app, span)` is an async generator with one `yield`. Keep `app.use("/", same_origin(), security_headers())`: it is the CSRF guard, so add no CSRF tokens.
- A handler is `async def (c: Context, w: Writer) -> None`. A page class's fields are its dependencies (`db`, `relay`, an API client), built in `bootstrap`. No service classes, repositories, base pages, or `utils`.
- Reads and writes are functions in `app/data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`. Every outside value is a `:name` parameter.
- A page imports `app.urls`, `app.data`, and `app.layout`, never another page. Markup that pages share goes in `app/layout.py`.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string (skill `stario-client`).

## Change an existing app

An app keeps its layout (an older one has `app/features/<page>/`). `grep -rn 'Route("' app` lists every URL and its file; read that page, `app/urls.py`, and the part of `app/data.py` it uses. A table with rows changes shape in `schema`, never dropped or recreated (skill `stario-litewriter`). Run the tests before and after. `tests/test_pages.py` and what it imports are generated: do not read or edit them.

## Skills

| The task needs | Skill |
| --- | --- |
| Sign-up and sign-in (password, Google, GitHub), protected pages, rows per user | `stario-auth` |
| A new column on a table that holds rows | `stario-litewriter` |
| A sort or filter in the URL, search as you type | `stario-view` |
| State in memory, an edit dialog, a message to one tab | `stario-relay` |
| Tests for a page, go to the page a command made, a navbar count | `stario-feature` |
| An outside HTTP API, cookies, uploads, errors, a name this file lacks | `stario-api` |
| A `h.*`, `data.*`, or `at.*` option this file lacks | `stario-datastar` |
| Slow work, a timer loop | `stario-jobs` |
| JavaScript | `stario-client` |
| Tailwind and DaisyUI | `stario-tailwind-daisyui` |
| A browser or a screenshot | `stario-browser-check` |

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

<!-- END stario-create -->

## This app

Notes for this app go below, under 4 KB; a deep topic gets its own file, named here in one line ("Read `EDITOR.md` first."). `stario-create sync` keeps everything below the END line.
