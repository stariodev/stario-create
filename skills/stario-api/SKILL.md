---
name: stario-api
description: Every Stario import path and signature, server side - serve on a host and port, routes, a catch-all and a 404 page, Context, Request, Writer, redirects, errors, cookies and a signed session, forms, static files, JSON, litewriter (SQLite), Relay, and TestClient (JSON, form posts, streams). Read it once before you write Stario code, and look names up here instead of in site-packages. The page side (h.*, data.*, at.*, SSE) is in stario-datastar.
---

# The Stario API, server side

Verified against stario 5.8 and litewriter 0.3. Do not read `site-packages`: pyrefly checks each call.

```python
from stario import App, Assets, Context, Files, RedirectException, Relay, Route, Span, Writer, serve
from stario import ServerConfig, classes, h  # ServerConfig is in `stario`, not `stario.http`
from stario.http import catch_errors, same_origin, security_headers
from stario.cookies import SignedCookie, delete_cookie, set_cookie
from stario.forms import read_form
from stario.json import dumps, loads
from stario.markup import HtmlElement, baked, render
from stario.datastar import SSE, at, data, read_signals
from stario.testing import TestClient
from litewriter import LiteWriter, Tx
import apsw  # apsw.ConstraintError: a UNIQUE or CHECK failed
```

## Serve

`asyncio.run(serve(bootstrap))` reads `STARIO_HOST` and `STARIO_PORT` (default `127.0.0.1:8000`). A platform that gives `$PORT`: start with `STARIO_HOST=0.0.0.0 STARIO_PORT=$PORT uv run python -m app.main`. In code instead: `serve(bootstrap, config=ServerConfig(host=..., port=...))`; then no `STARIO_*` variable is read. A setting of the app is a field of `Config` with a default; `from_env` reads `FIELD_NAME` (`db_path` from `DB_PATH`, cast to the type of the default).

## App and Route

```text
app.add(ROUTE, handler, middleware=[...])   # one method on one path
app.use("/prefix", mw1, mw2)            # middleware is (inner: Handler) -> Handler
app.not_found("/", handler)             # custom 404 for every path under the prefix
app.create_task(coro, name=None)        # tracked; Stario waits for it on shutdown
app.shutting_down   app.shutdown        # a timer loop reads app.shutdown once

ROUTE = Route("GET /rooms/{room_id}")   # a GET route answers HEAD too
FILES = Route("GET /docs/{path...}")    # catch-all: the rest of the path, last segment only
ROUTE.href(7, query={"sort": "title"}, fragment=None)   # "/rooms/7?sort=title"
```

A literal segment beats a parameter: `/editor` and `/editor/{slug}` both work. An unknown path gets `404 Not Found` (text) unless `app.not_found` sets a page; a known path with another method gets 405.

## Context `c` and Request `c.req`

```text
c.req.method  c.req.path  c.req.host
c.req.query                    # ParsedQuery: .get(key, default), .getlist(key), key in
c.req.headers.get(name, default)   c.req.headers.get("datastar-request")  # set on a Datastar action
c.req.cookies.get(name, default)
await c.req.body(max_size=None)   # bytes; 10 MiB by default, past it 413
c.match.params                 # path captures: dict of str
c.state                        # middleware fills it; read via a typed function
c.alive(source)                # async iterator until the client leaves or the app drains
c.app  c.span
```

## Writer `w`

```text
w.html(node_or_str, status=200)
w.text("why", status=400)
w.json(value, status=200)
w.empty()                      # 204
w.redirect(url, status=307)    # after a plain form POST use status=303
w.respond(body_bytes, b"text/csv", status=200)
w.headers.set(name, value)     # before the answer
raise RedirectException(303, url)   # from any depth of a handler: becomes a redirect
```

A Datastar request (`at.post(...)`) follows no redirect: answer it with `SSE(w).navigate(url)`.

## Errors

An uncaught exception logs on the request span and answers 500. A typed error to a response:

```python
async def not_allowed(c: Context, w: Writer, exc: BaseException) -> None:
    w.text("not allowed", status=403)

app.use("/", catch_errors(PermissionError, respond=not_allowed))
```

## Cookies and a signed session

```python
jar = SignedCookie("__Host-session", keys=[secret])  # secret: 32+ bytes, from Config
jar.set(w, {"user": user_id})  # signed JSON, httponly, secure, samesite=lax, 14 days
value = jar.get(c.req)  # SignedValue | None; value.data["user"]
jar.delete(w)
set_cookie(w, "theme", "dark", max_age=None, httponly=True, samesite="lax")
delete_cookie(w, "theme")
```

The browser keeps a `secure` cookie on `http://localhost` too; `TestClient` keeps it. The payload is readable: store an id, never a secret. Sign-in, `Session.attach`, `current_user(c)`, passwords: skill `stario-auth`.

## Forms

A Datastar action sends signals: `signals = await read_signals(c.req)` (a dict; a GET sends them in `?datastar=`). A plain `<form method="post">` or an upload:

```python
with await read_form(c.req) as form:
    title = form.get("title", "")
    tags = form.getlist("tags")
    photo = form.file("photo")  # UploadFile | None; await photo.read()
```

## Static files

```python
ASSETS = Assets(STATIC_DIR, url_prefix="/static")  # fingerprinted, cached forever
STYLE_CSS = ASSETS.href("css/style.css")  # "/static/css/style.<hash>.css"
UPLOADS = Files(config.data_dir / "uploads", "/uploads")  # live files, ETag
# in bootstrap: span.attrs(await ASSETS.attach(app)); await UPLOADS.attach(app)
```

`ASSETS.href` raises at import when the file is missing. A file the spec gives: copy it into `static/`.

## JSON

`stario.json.dumps(value) -> str`, `loads(text)`. `w.json(value)` answers JSON.

## litewriter (SQLite)

```text
async with LiteWriter(path, schema=fn, claim=30) as db:   # in bootstrap; schema(tx) runs once
db.query(sql, Row, **params)   # list of Row(*columns); without Row, tuples
db.one(sql, Row, **params)     # Row or None
db.value(sql, **params)        # first column of the first row; raises when there is none
await db.write(fn, *args)      # fn(tx, *args) in one transaction; returns fn's value
async with db.watch(sql, Row, **params) as rows:   # first item now, then after each change
    async for items in c.alive(rows): ...
tx.execute(sql, **params)  tx.query  tx.one  tx.value  tx.last_insert_rowid()
```

`:name` in the SQL takes the keyword `name`. Reads are plain calls on the loop. A write function holds no network call and no password hash: do that before `db.write`. Catch `apsw.ConstraintError` around `await db.write(...)` for a taken unique value. Tables: skill `stario-feature`; schema changes: `stario-litewriter`.

## Relay

```text
relay: Relay[dict] = Relay()            # one, built in bootstrap
relay.publish("article.7", {})          # dotted subject
async with relay.subscribe("article.7", latest=True) as events:   # also "article.*", "*"
    async for subject, payload in c.alive(events): ...
```

## Middleware and Span

- `same_origin()`: a cross-site `POST` gets 403. `TestClient` and curl send no `Origin`, so they pass.
- `security_headers()`: `nosniff`, `x-frame-options: DENY`, a referrer policy. No CSP.
- A middleware method: `def attach(self, inner: Handler) -> Handler:` returns `async def handler(c, w)`.
- `c.span.event("todo.added", {"id": 7})`, `c.span.attrs({...})`, `c.span.fail("why")`.

## TestClient

```text
async with TestClient(bootstrap, request_timeout=5) as client:   # the `client` fixture
    r = await client.get(url, params={"datastar": '{"q": "x"}'})
    r = await client.post(url, json={"title": "milk"})       # a Datastar action
    r = await client.post(url, data={"email": "a@b.c"})      # a plain form, urlencoded
    r = await client.post(url, files={"photo": ("a.png", b"...", "image/png")})
    r = await client.get(url, follow_redirects=False)        # r.headers.get("location")
    r.status_code  r.text  r.json()  r.url (a str)  r.headers.get(name)  r.cookies
    async with client.stream("GET", LIVE.href(), timeout=2) as live:
        events = live.iter_events()            # dicts with "event" and "data"
        first = (await anext(events))["data"]
    await client.drain_tasks()                 # wait for create_task work
```

The client keeps cookies in `client.cookies` (a dict): `client.cookies.clear()` signs out, and saving and restoring it switches users. Buffered calls follow redirects. A `navigate` answer contains `window.location`. Read the first stream event before the command, so the subscription is up.
