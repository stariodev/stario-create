<!-- BEGIN stario-create -->
# Stario app guide

A Stario app is Python 3.14: the server renders `h.*` tags, Datastar (`data.*`, `at.*`) sends
commands and keeps pages live over SSE, litewriter keeps SQLite (stario 5.8, litewriter 0.3).
The names are here or in a skill: never read `site-packages`.

## The loop

1. Start in one command, kits included (a kit replaces only files still equal to the scaffold):
   `uvx stario-create@latest new app --db && cd app && uvx stario-create@latest add auth --password`.
   Kits: `add auth --password` (email and password), `add auth` (Google, GitHub), `add tailwind`
   (Tailwind, DaisyUI, no Node). `new` prints the files you change: do not open them.
2. Read the spec and tests, several files per command. Plan every route.
3. Write `app/urls.py` (every route), `app/data.py` (tables, rows, SQL), `app/layout.py`
   (shared markup), `app/pages/<area>.py` (several pages per module), then `app/main.py` (one
   register line per page class). Send several files per message. Import what a file uses;
   do not tidy imports or unused names by hand: `check` sorts and drops them.
4. `uvx stario-create@latest check`: format, lint, types, the page check, the tests. Each problem
   names its fix. Repeat until `check: ok`.
5. See a page with no server: `uvx stario-create@latest request GET /bookmarks`. Each call starts
   on an empty database, so chain steps: `request POST /signup -d email=a@b.co -d password=12345678
   -d username=a GET /bookmarks` (`-d` a form field, `-j JSON` a Datastar action, `-s JSON` signals
   on a GET).
6. An acceptance suite (`npm test`): run it in the foreground with the Bash tool's timeout
   (600000), never in the background. Fix, rerun. When it passes, stop: no screenshots, no own
   tests. No suite: write TestClient tests (skill `stario-tests`).

Shell: macOS has no `timeout` command; `sed -i ''`. Stop a server from an earlier call by port:
`lsof -ti tcp:8000 | xargs kill`, never `pkill -f` (it stops other apps). `python -m app.main`
listens on `STARIO_HOST:STARIO_PORT` (127.0.0.1:8000); for a runner's `PORT`, set
`STARIO_PORT=$PORT`. `Config` already reads `DATABASE_PATH` (the SQLite file).

Changing an app that holds data: read `app/urls.py`, `app/data.py` and the pages to change first.
A new column on a table with rows: skill `stario-migrate` (never drop and create). A new table
is one more `CREATE TABLE IF NOT EXISTS`.

## A page: list, search, paging, live stream, a command

```python
# app/urls.py (add)
BOOKMARKS = Route("GET /bookmarks")
BOOKMARKS_LIVE = Route("GET /bookmarks/live")
ADD_BOOKMARK = Route("POST /bookmarks")
```

```python
# app/data.py
from dataclasses import dataclass

from litewriter import LiteWriter, Tx

PER_PAGE = 20


def schema(tx: Tx) -> None:
    """Runs at each start: every statement is IF NOT EXISTS."""
    tx.execute(
        "CREATE TABLE IF NOT EXISTS bookmarks (id INTEGER PRIMARY KEY,"
        " title TEXT NOT NULL, url TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')))"
    )


@dataclass(frozen=True, slots=True)
class Bookmark:
    id: int
    title: str
    url: str


# A stream repaints when this result changes: it changes with every write the page shows.
CHANGES = "SELECT count(*), max(id) FROM bookmarks"
_MATCH = "instr(lower(title), lower(:q)) > 0"  # literal search: % and _ match themselves


def list_bookmarks(db: LiteWriter, q: str, page: int) -> tuple[list[Bookmark], int]:
    sql = f"SELECT id, title, url FROM bookmarks WHERE {_MATCH} ORDER BY id DESC"
    rows = db.query(
        f"{sql} LIMIT :n OFFSET :skip", Bookmark, q=q, n=PER_PAGE, skip=(page - 1) * PER_PAGE
    )
    total: int = db.value(f"SELECT count(*) FROM bookmarks WHERE {_MATCH}", q=q)
    return rows, total


def add_bookmark(tx: Tx, title: str, url: str) -> int:
    return tx.value(
        "INSERT INTO bookmarks (title, url) VALUES (:t, :u) RETURNING id", t=title, u=url
    )
```

```python
# app/pages/bookmarks.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, classes, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import CHANGES, PER_PAGE, Bookmark, add_bookmark, list_bookmarks
from app.layout import page
from app.urls import ADD_BOOKMARK, BOOKMARKS, BOOKMARKS_LIVE


@dataclass(frozen=True, slots=True)
class BookmarksPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(BOOKMARKS, self.show)
        app.add(BOOKMARKS_LIVE, self.live)
        app.add(ADD_BOOKMARK, self.add)

    def listing(self, c: Context) -> HtmlElement:
        """The live part, read from the URL query: the page and its stream send this element."""
        q, raw = c.req.query.get("q", "").strip(), c.req.query.get("page", "1")
        n = int(raw) if raw.isdecimal() and raw != "0" else 1
        return render_list(q, n, *list_bookmarks(self.db, q, n))

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(c.req.query.get("q", ""), self.listing(c)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(CHANGES) as changes:
            async for _ in c.alive(changes):  # now, then after each change, until the tab closes
                sse.patch_elements(self.listing(c))

    async def add(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        title, url = str(signals.get("title", "")).strip(), str(signals.get("url", "")).strip()
        if not title or not url.startswith(("https://", "http://")):
            SSE(w).patch_signals({"_error": "a title and an http(s) URL are required"})
            return
        await self.db.write(add_bookmark, title, url)
        SSE(w).patch_signals({"title": "", "url": "", "_error": ""})  # the streams repaint


def render_list(q: str, n: int, rows: list[Bookmark], total: int) -> HtmlElement:
    pages = range(1, (total + PER_PAGE - 1) // PER_PAGE + 1)
    return h.Section(
        {"id": "bookmarks"},
        data.init(at.get(BOOKMARKS_LIVE.href(query={"q": q or None, "page": n}))),
        h.Ul(*[h.Li(h.A({"href": b.url}, b.title)) for b in rows]),
        None if rows else h.P("No bookmarks yet."),
        h.Nav(*[
            h.A(
                classes({"active": p == n}),
                {"href": BOOKMARKS.href(query={"q": q or None, "page": p})},
                str(p),
            )
            for p in pages
        ]),
    )


def render(q: str, listing: HtmlElement) -> HtmlElement:
    return page(
        "Bookmarks",
        h.Main(
            {"id": "main"},
            data.signals({"title": "", "url": "", "_error": ""}),
            h.Form(
                {"method": "get", "action": BOOKMARKS.href()},
                h.Input({"type": "search", "name": "q", "value": q}),
            ),
            h.Form(
                data.on("submit", at.post(ADD_BOOKMARK.href()), prevent=True),
                h.Input({"placeholder": "Title"}, data.bind("title")),
                h.Input({"placeholder": "https://..."}, data.bind("url")),
                h.Button({"type": "submit"}, "Add"),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
            ),
            listing,
        ),
    )
```

`app/main.py`: import `BookmarksPage`; in bootstrap, `BookmarksPage(db).register(app)`. Link the
page in `LINKS` of `app/pages/home.py`. That file owns `GET /`: a task with its own home page
rewrites it (a second `GET /` raises).

## Names

- Every HTML tag is `h.<Name>`. Attribute dicts, `classes(...)` and `data.*` come before the
  children (text, tags, `None`, `*list`). A list of nodes in a variable is `list[HtmlElement]`.
  `SafeString(html)` is for trusted HTML only.
- Request: `c.req.query.get("q", "")`, `.getlist("tag")`, `c.match.params["slug"]` (a `str`),
  `c.req.cookies.get("k")`, `c.req.headers.get("k")`.
- Answer once: `w.html(el)`, `w.text("not found", status=404)`, `w.json(v)`, `w.empty()`,
  `w.redirect(url, 303)`, `w.respond(body, b"text/csv")`. A Datastar action answers through
  `SSE(w)`: `.patch_signals`, `.patch_elements(el)` (morphs the element with that id;
  `mode="append", selector="#list"` adds), `.remove("#id")`, `.navigate(url)`; or `w.empty()`.
- Plain form: `h.Form({"method": "post", "action": R.href()}, ...)`; `form = await read_form(c.req)`
  (`stario.forms`), `form.get("title", "")`, `form.getlist("tag")`; then `w.redirect(url, 303)`, or
  the page again with its errors, `w.html(..., status=422)`.
- Routes: `Route("GET /tags/{tag}")`, `{path...}` takes the rest; `R.href("x", query={"page": 2})`
  drops `None` values. `app.use("/admin", middleware)`; `app.not_found("/", handler)`.
- A row's button: `data.on("click", at.post(DONE.href(item.id)))`; a missing or another user's
  row answers 404. Search as you type: an input with `data.bind("q")` and `data.on("input",
  at.get(RESULTS.href()), debounce="300ms")`; that handler reads `read_signals` and patches.
- Data: `db.one(sql, Row, **p)` is a row or None; `db.value` raises `QueryError` on no row. In a write:
  `tx.execute`, `tx.value`, `tx.one`, `tx.query`. A taken unique value raises `apsw.ConstraintError`.
- Static: `ASSETS.href("css/x.css")` renames to `x.<hash>.css`. A URL that must keep its file name
  (a default avatar): `MEDIA = Files(ASSETS.directory / "media", "/media")` in
  `app/layout.py`, `await MEDIA.attach(app)` in bootstrap, `MEDIA.href("avatar.svg")`.
- `set_cookie(w, "k", value, max_age=86400)` (`stario.cookies`). `from stario.json import dumps,
  loads`; `loads` returns `object`: `cast(list[str], loads(s))`.
- A setting is one field with a default in `Config` (`site_url: str = ""` reads `SITE_URL`;
  no `os.environ`), passed from bootstrap to page classes. State lives in objects, not modules.

## Rules that bite

- `page()` in `app/layout.py` is `@baked`: it runs once at import with placeholders, so an `if`,
  `==`, f-string or loop on its parameters raises. Compute first. A per-request part (a signed-in
  header) is a new parameter that every caller passes.
- A write function (`fn(tx, ...)`) makes no network call and hashes no password: do that first,
  slow work through `await asyncio.to_thread(...)`.
- `watch` wakes on a commit to a table it reads and yields only when its result changes. Watch
  something every shown edit changes: `max(updated)`, the edited columns, a count per table.
- `ORDER BY` takes no parameter: pick the SQL text from a dict, `SORTS = {"new": "id DESC"}`.
- A Datastar action follows no redirect: `SSE(w).navigate(url)`. A duration is a string, `"300ms"`.
- Do not read or edit the generated `tests/test_pages.py`, `_pagecheck.py`, `_lint.py`,
  `test_js.py`: the page check opens every page and stream and names what is wrong.

## Accounts

`add auth --password` writes `app/auth/` (users table, `Session`, hashes) and `app/pages/login.py`
(plain forms: `/login`, `/signup`, `POST /logout`) with `tests/test_login.py`. Change paths in
`app/urls.py`, labels and markup freely; keep the route names and the fields `email`, `password`,
`username`, and the tests hold. User columns go in `CREATE TABLE users` (`app/auth/data.py`).
Protect a prefix in `app/main.py`: `app.use("/settings", session.require)`. In a handler,
`current_user(c)` is the user id or None; `signed_in_user(c)` behind `require`.

## Skills

Load one only when a task needs it: `stario-tests` (TestClient tests, when no acceptance suite),
`stario-migrate` (tables that already hold rows), `stario-outside-api` (another service over HTTP),
`stario-js` (any JavaScript file), `stario-background` (state in memory, slow jobs, timers),
`stario-accounts` (past the kit: Google setup, roles, tokens), `stario-reference` (a name this
file lacks or pyrefly rejects).

<!-- END stario-create -->

## This app

Notes for this app, under 4 KB. `sync` keeps this section.
