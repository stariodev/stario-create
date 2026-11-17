<!-- BEGIN stario-create -->
# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia: a handler writes HTML, Datastar morphs it into the page, and one open SSE response keeps a page live. Not ASGI: no Uvicorn, FastAPI, or Jinja.

## The loop

1. `uvx stario-create@latest new app --db` where the app lives (`app`, `.`). Run it without `| tail`: it prints the files you will edit, so you need not open them. Then `cd` into the app folder; every path below starts there.
2. A kit runs before you edit any file (it replaces only unchanged files): accounts with a password `uvx stario-create@latest add auth --password`; Google or GitHub sign-in `add auth`; Tailwind `add tailwind`.
3. Write every file in one message: several Write calls, or one command with a heredoc per file. Write the imports each file uses. Leave imports to the check (it sorts them and drops unused ones): do not reopen or tidy a file you just wrote. `uvx stario-create@latest add page NAME...` (`article=/article/{slug}`) writes page files, routes, and links.
4. `just check` (without `just`: `uvx stario-create@latest check`) formats, lints, type-checks, tests, and prints only problems, each with its fix. Fix what it says; never read `site-packages`.
5. When the task ships an acceptance suite (`npm test`, Playwright), that suite is the check: run it after `just check`, in the foreground (never in the background with `sleep` or Monitor), and stop when both pass. Write no tests of your own for it. Without one, each page gets one test file (skill `stario-feature`).
6. See a page without a server: `uvx stario-create@latest request GET /todos` prints the HTML or the first stream events (`POST /todos -j '{"title": "x"}' GET /todos`: an action, then a read; each call starts on an empty database). Stop a server you started by port (`lsof -ti :8000 | xargs kill`), never `pkill -f` (it stops other apps). macOS has no `timeout`, and its `sed -i` needs `''`.

A platform that gives `$PORT`: `STARIO_HOST=0.0.0.0 STARIO_PORT=$PORT uv run python -m app.main`. A setting is a field with a default in `Config` (`app/config.py`); `from_env` reads its name in capitals. A database file named by an env var (`DATABASE_PATH`): a field `database_path: str = ""`, and the `db_path` property returns `Path(self.database_path)` when set.

## Imports

```python
from stario import App, Context, Route, Writer, classes, h
from stario.datastar import SSE, at, data, read_signals  # not from `stario`
from stario.datastar.format import string_literal  # user text inside an expression
from stario.forms import read_form
from stario.json import dumps, loads  # loads returns object: cast(list[str], loads(s))
from stario.markup import HtmlElement
from litewriter import LiteWriter, Tx
import apsw  # apsw.ConstraintError: a UNIQUE or CHECK failed
```

## A live page

A page on shared state has three routes. `show` sends the first HTML; after that only the stream sends HTML. The stream follows `db.watch(sql)`, so a command validates, writes, and replies, and never renders.

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


def schema(tx: Tx) -> None:
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

- `render` returns the whole document from its arguments. Keep the element with `data.init` and `data.signals(..., if_missing=True)` the same in every render (tag, `id`, attributes), so what the user typed survives each repaint.
- A signal named `_x` stays in the tab: the server can set it, the browser never sends it.
- A page on several tables watches one small query that changes whenever anything shown changes (`SELECT count(*), max(updated) FROM comments WHERE article_id = :id`) and reads the rest in the loop.
- A page on state that cannot change while it is open is static: `show` only, no stream.
- A task that defines `/`: rewrite `app/pages/home.py` and keep `HOME` (a second `GET /` raises).

## Commands

1. Read: `await read_signals(c.req)` (a dict); `c.match.params["id"]` (a string: check, then convert). A plain `<form method="post">` or an upload: `with await read_form(c.req) as f: f.get("title", "")`.
2. Validate: a bad value gets `SSE(w).patch_signals({"_error": "why"})`, a missing row `w.text("not found", status=404)`, then `return`. A taken unique value: catch `apsw.ConstraintError` around `await self.db.write(...)` and patch `_error`.
3. Write: `await self.db.write(fn, *args)`; `fn(tx, ...)` lives in `app/data.py` and holds no network call and no password hash.
4. Reply once: `w.empty()`, `SSE(w).patch_signals(...)` (a confirmation: `{"_toast": "Saved."}`), or `SSE(w).navigate(url)`. A plain form answers `w.redirect(url, status=303)`. Only a command navigates: a stream whose row is gone just returns.

A GET never changes state. A sort, filter, or page number is the URL query, reached by `<a href>` (skill `stario-view`).

## Names

```text
h.Div(...)  # every HTML tag is h.<Name>; nodes kept in a variable are list[HtmlElement]
w.html(node)  w.text(s, status=400)  w.json(v)  w.empty()  w.redirect(url, status=303)  # pass 303: the default is 307
SSE(w).patch_elements(node)  .patch_signals({...})  .navigate(url)
ROUTE.href(7, query={"page": 2})   Route("GET /docs/{path...}")
c.req.query.get(k, default)  c.req.cookies.get(k)  c.alive(source)  c.app.create_task(coro)
db.query(sql, Row, **p) -> list   db.one(...) -> Row | None   db.value(sql, **p)  # raises on no row   await db.write(fn, *a)
tx.execute(sql, **p)  tx.query  tx.one  tx.value   # in fn(tx, ...): UPDATE, DELETE
data.on("click", expr, prevent=True, debounce="300ms")  # a bare number is seconds
data.attr("disabled", "$_saving")  data.indicator("_saving")  data.class_("on", expr)
data.ref("_dialog")  data.ignore_morph()  at.delete(url)
```

`h.*`: attributes first (a dict, `classes("btn", {"on": on})`, each `data.*`), then children. `classes` never goes inside the dict. `True` writes a bare attribute; `None` leaves it out. A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.

`ASSETS.href` renames a file (`a.<hash>.svg`); a file whose name a test or link needs: `Files(dir, "/media")` (skill `stario-api`).

## Rules

- Keep `app.use("/", same_origin(), security_headers())`: it is the CSRF guard, so add no CSRF tokens.
- A page class's fields are its dependencies (`db`, `relay`, an API client), built in `bootstrap`. No service classes, repositories, or `utils`.
- Reads and writes are functions in `app/data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`. Every outside value is a `:name` parameter.
- A page may import any module under `app/` except another page. Markup that pages share goes in `app/layout.py`.
- `page()` in `app/layout.py` is `@baked`: it runs once with placeholders, so no `if`, `==`, or f-string on a parameter. Build a per-request part (a signed-in navbar) in the page and pass it in.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string (skill `stario-client`).

## Change an existing app

Keep the app's file layout. `grep -rn 'Route("' app` lists every URL and its file; read that page, `app/urls.py`, and the part of `app/data.py` it uses. A table with rows changes shape in `schema`, never dropped or recreated (skill `stario-litewriter`). `just test` before you change anything, `just check` after. `tests/test_pages.py` and what it imports are generated: do not read or edit them.

## Skills

When the task matches a row, load that skill before you write code for it.

| The task needs | Skill |
| --- | --- |
| Sign-up and sign-in (password, Google, GitHub), protected pages, rows per user | `stario-auth` |
| A change to a table that already holds rows; a stream that does not repaint | `stario-litewriter` |
| A sort, filter, or page number in the URL; search as you type | `stario-view` |
| An outside HTTP API (a client, a cache, a fake for tests) | `stario-outside-api` |
| State in memory, an edit dialog, a message to one tab | `stario-relay` |
| Tests for a page, go to the page a command made, a navbar count | `stario-feature` |
| Cookies, uploads, static files, error pages, a server name this file lacks | `stario-api` |
| A `h.*`, `data.*`, `at.*`, or `SSE` option this file lacks; `@baked` | `stario-datastar` |
| Slow work, a timer loop | `stario-jobs` |
| JavaScript | `stario-client` |
| Tailwind and DaisyUI | `stario-tailwind-daisyui` |
| A browser or a screenshot | `stario-browser-check` |

<!-- END stario-create -->

## This app

Notes for this app go below, under 4 KB; a deep topic gets its own file, named here in one line ("Read `EDITOR.md` first."). `stario-create sync` keeps everything below the END line.
