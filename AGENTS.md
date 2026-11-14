# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia. A handler writes HTML. Datastar morphs it into the page. One open SSE response keeps a page live. State lives on the server. Not ASGI: no Uvicorn, FastAPI, Jinja, or response objects. Docs: https://stario.dev/docs.

This file holds the rules and the shape of a page. Two skills hold every import path and signature: `stario-api` (server: the port, a 404 page, redirects, errors, cookies, forms, static files, SQLite, tests) and `stario-datastar` (page: `h.*`, `data.*`, `at.*`, `SSE`). Read both once before you write code. Never read the stario source in site-packages: what they do not list, pyrefly checks.

The last section of this file holds the notes of this app, under 4 KB. A deep note on one topic goes in its own file, named by a line such as "Read `EDITOR.md` before you change the editor."

## Start an app

```bash
uvx stario-create@latest new app --db   # the folder: `app`, `.`, any path; --db adds SQLite
```

One command, run where the app should live. It installs the dependencies, writes a tested app, runs its tests, and prints what each file holds. Do not open the files to learn them: `app/main.py` is below, and the rest is the layout in the next section. Without `--db`, `main.py` has no `LiteWriter` and no `schema`.

```python
async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db:
        app.use("/", same_origin(), security_headers())
        span.attrs(await ASSETS.attach(app))
        # pages: one register line each; a page with data gets `db`
        HomePage(config.app_name).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))  # listens on STARIO_HOST:STARIO_PORT, default 127.0.0.1:8000
```

`schema(tx)` above it creates the tables. Run the app with `just dev` (reloads) or `just serve`. Another host or port: `STARIO_HOST=0.0.0.0 STARIO_PORT=4000 uv run python -m app.main`. Yard sets `STARIO_HOST`, `STARIO_PORT`, and `PROJECT_DATA_DIR`.

## Layout

```text
app/main.py           bootstrap: shared objects, one register line per page
app/config.py         Config: one field with a default per setting; from_env reads FIELD_NAME
app/assets.py         ASSETS (static/ at /static), STYLE_CSS, DATASTAR_JS, SCRIPTS
app/common/shell.py   page(title, body): the <html> document
app/features/<page>/  urls.py (Routes), views.py (render), handlers.py (the page class), data.py (SQL)
app/<name>/           code with no URL; never imports features/
static/css/ static/js/   files the pages load: ASSETS.href("css/app.css")
tests/test_<page>.py  tests/conftest.py has the `client` fixture
```

- A page is one folder, named after the URL noun: `/rooms/{room_id}` is `room`. It gets one line in `LINKS` in `app/features/home/views.py`.
- A feature may import the `urls.py` and `data.py` of another feature, never its views or handlers. Shared markup (a nav bar, a card) goes in `app/common/`.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string (skill `stario-client`).

## Rules

- `bootstrap(app, span)` is an async generator with one `yield`. Keep `app.use("/", same_origin(), security_headers())`. `same_origin()` is the CSRF guard: add no CSRF tokens. It does not check GET, so a GET never changes state.
- A handler is `async def (c: Context, w: Writer) -> None`. It answers once: `w.html`, `w.text`, `w.json`, `w.empty`, `w.redirect`, or `SSE(w)`.
- `Route("GET /rooms/{room_id}")` is one method on one path; a GET route answers HEAD too. `ROUTE.href(room_id, query={...})` builds the URL. No `url_for`.
- `c.match.params` values are strings: check, then convert. `c.req.query.get("page", "1")`.
- In `h.*`, attributes come first, children after: `h.A({"href": url}, classes("btn", {"on": on}), data.show("$x"), "text")`. A dict, `classes(...)`, and each `data.*` are attributes; `classes` never goes inside the dict. A dict after a child raises "HTML attributes must be passed before children" when the page renders, not at import. Helper types: `stario-datastar`.
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
3. Reply: `w.empty()`, `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)` to go to another page.
4. Execute: `await db.write(...)`, or change memory, then `relay.publish(...)`.

## A page in code

```python
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
        async with self.db.watch(ALL_TODOS, Todo) as rows:
            async for todos in c.alive(rows):
                sse.patch_elements(render(todos))

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not title:
            SSE(w).patch_signals({"_error": "title can't be blank"})
            return
        SSE(w).patch_signals({"title": "", "_error": ""})
        await self.db.write(add_todo, title)


def render(todos: list[Todo]) -> HtmlElement:  # views.py
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
- A busy form: `data.indicator("_saving")` on the `<form>`, `data.attr("disabled", "$_saving")` on its button. A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.
- A page with several tables: watch one small query that changes when the page should (`SELECT count(*), max(id) FROM comments WHERE article_id = :id`), and read the rest inside the loop.

A page is one class in `handlers.py`; its fields are its dependencies. A read or a write is a function in `data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`. No service classes, repositories, base pages, or `utils`. The skill `stario-feature` is a whole page with its tables, views, and tests, ready to copy.

## Write in few steps

Plan the routes, tables, and shared markup first. Then write the app in a few large steps: one command (a chain of heredocs, or several writes in one message) can create ten files, and a feature (`urls.py`, `data.py`, `views.py`, `handlers.py`) is never split across steps. Do not reopen a file you just wrote to tidy it: let `just check` and the tests say what is wrong. A wrong name costs a rewrite: look it up in the skills before you write it.

## Tests

`tests/conftest.py` gives `client`, a `TestClient(bootstrap)` on an empty data dir. A `GET` sends signals in `params={"datastar": '{"q": "x"}'}`, a Datastar `POST` in `json={...}`, a plain form in `data={...}`. The next SSE event of `client.stream(...)` is the changed HTML; two streams are two tabs. `tests/test_pages.py` checks every page by itself.

Test what nothing else checks. When the task comes with acceptance tests (an end-to-end suite such as `npm test`), that suite is the check: write no TestClient tests for what it covers, run it after each change, and stop when it passes. Without such a suite, each page gets one test file: it loads, a command repaints the stream, bad input is refused. A bug starts with a test that shows it.

## Checks

Change a file with the Edit tool. Run Python as `uv run python`. Run `just check` before you finish and after a failure: it formats, fixes lint, checks types, runs the tests, and prints only problems. pyrefly checks each call, so trust Stario, Datastar, and litewriter. Run a long test suite in the foreground and wait for it; do not poll a background run.

A browser is only for client JS that holds state. No computer use. When the user watches the app, the user is the browser: say what to look at. When it does not work: `curl` their server, then a failing test (skill `stario-browser-check`).

## Which skill

- A page with SQLite, a form, a live list: this file, then `stario-feature` for the whole recipe.
- Sign-in, sessions, accounts, passwords: `stario-auth`.
- A sort, a filter, paging, a search as you type: `stario-view`.
- State in memory, a message to one tab, an edit dialog: `stario-relay`.
- A table that already holds rows changes shape (a new field, a dropped column): `stario-litewriter`.
- Work that takes seconds, or a loop on a timer: `stario-jobs`.
- JavaScript: `stario-client`. Tailwind and DaisyUI: `stario-tailwind-daisyui`. Before a browser: `stario-browser-check`.

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

## This app

Notes for this app go below. `stario-create sync` replaces the text above and keeps this section.
