---
name: stario-api
description: Stario server names beyond AGENTS.md - an outside HTTP API with a cache and a test fake, cookies, uploads, static files, errors, TestClient options. Use when AGENTS.md lacks a server name or pyrefly rejects one. Not for h.*, data.*, at.*.
---

# The Stario API, server side

Verified against stario 5.8. AGENTS.md has the imports, `w.*`, `SSE`, and `db.*`; this file has the rest. pyrefly checks each call, so do not read `site-packages`.

```python
from stario import App, Assets, Files, ServerConfig, Span, serve  # not from stario.http
from stario.http import catch_errors, same_origin, security_headers
from stario.cookies import SignedCookie, delete_cookie, set_cookie
from stario.markup import baked, render
from stario.testing import TestClient
```

## Serve and settings

`asyncio.run(serve(bootstrap))` reads `STARIO_HOST` and `STARIO_PORT`. In code instead: `serve(bootstrap, config=ServerConfig(host=..., port=...))`; then no `STARIO_*` variable is read. A setting is a `Config` field with a default; `from_env` reads its name in capitals (`app_name` from `APP_NAME`) and casts it to the type of the default. `db_path` is a property, so no variable sets it.

## App, Route, Context

```text
app.add(ROUTE, handler, middleware=[...])   app.use("/prefix", mw1, mw2)
app.not_found("/", handler)             # a 404 page for every path under the prefix
app.create_task(coro, name=None)        # tracked; Stario waits for it on shutdown
app.shutting_down   app.shutdown        # a timer loop reads app.shutdown once (stario-jobs)
Route("GET /docs/{path...}")            # catch-all: the rest of the path
c.req.method  c.req.path  c.req.host  c.req.headers.get(name)  c.req.query.getlist(key)
await c.req.body(max_size=None)         # bytes; past 10 MiB by default, 413
c.state                                 # middleware fills it; read it through a typed function
c.span.event("todo.added", {"id": 7})  c.span.attrs({...})  c.span.fail("why")
w.respond(body, b"text/csv", status=200)   w.headers.set(name, value)   # before the answer
```

`href` percent-encodes each value; a value with `/` raises (use `{path...}`). A literal segment beats a parameter: `/editor` and `/editor/{slug}` both work. An unknown path gets a text 404 unless `app.not_found` sets a page; another method on a known path gets 405. A missing row in a handler: `w.html(not_found_page(), status=404)`.

## Errors and redirects

`raise RedirectException(303, url)` from any depth of a handler becomes a redirect. A Datastar action follows no redirect: answer it with `SSE(w).navigate(url)`. An uncaught exception logs on the span and answers 500. A typed error to a response:

```python
async def not_allowed(c: Context, w: Writer, exc: BaseException) -> None:
    w.text("not allowed", status=403)


app.use("/", catch_errors(PermissionError, respond=not_allowed))
```

## Cookies

```python
jar = SignedCookie("__Host-prefs", keys=[config.cookie_secret])  # secret: 32+ bytes
jar.set(w, {"theme": "dark"})  # signed JSON, httponly, secure, samesite=lax, 14 days
value = jar.get(c.req)  # SignedValue | None; value.data["theme"]
jar.delete(w)
set_cookie(w, "theme", "dark", max_age=None, httponly=True, samesite="lax")
delete_cookie(w, "theme")
```

The payload is readable: store an id, never a secret. A browser keeps a `secure` cookie on `http://localhost` too. Sign-in and the session: skill `stario-auth`.

## Forms and uploads

```python
with await read_form(c.req) as form:
    title = form.get("title", "")
    tags = form.getlist("tags")
    photo = form.file("photo")  # UploadFile | None; await photo.read()
```

A file input bound with `data.bind` sends a `FileSignal` dict instead (`name`, `contents` in base64, `mime`).

## Static files

```python
UPLOADS = Files(config.data_dir / "uploads", "/uploads")  # live files, ETag
# in bootstrap: span.attrs(await ASSETS.attach(app)); await UPLOADS.attach(app)
```

`ASSETS.href("css/app.css")` gives a fingerprinted URL, cached forever, and raises at import when the file is missing. A file the spec gives: copy it into `static/`.

## JSON and an outside HTTP API

`loads(text)` returns `object`: narrow it (`cast(list[str], loads(s))`, or check `isinstance`). Stario has no HTTP client: `uv add httpx`, open one `httpx.AsyncClient` in `bootstrap`, and pass it to the pages like `db`. The whole recipe, with a cache and a test that needs no network: `references/outside-api.md`.

## Middleware

- `same_origin()`: a cross-site `POST` gets 403. `TestClient` and curl send no `Origin`, so they pass.
- `security_headers()`: `nosniff`, `x-frame-options: DENY`, a referrer policy. No CSP.
- A middleware with a dependency is a method: `def attach(self, inner: Handler) -> Handler:` returns `async def handler(c, w)`; register `app.use("/", session.attach)`.

## Tests

`TestClient` calls, the stream pattern, cookies, and `drain_tasks`: `references/testclient.md`. SQLite (`LiteWriter`, `watch`): skill `stario-litewriter`. `Relay`: skill `stario-relay`.
