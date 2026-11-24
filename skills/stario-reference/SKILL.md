---
name: stario-reference
description: Stario, Datastar and litewriter names past AGENTS.md - more data.* and at.* options, SSE morph modes, dialogs, infinite scroll, a live navbar count, uploads, signed cookies, middleware, error pages, server settings, JSON endpoints. Use when AGENTS.md lacks a name or pyrefly rejects one.
---

# Reference

Each line is one fact, checked against stario 5.9 and litewriter 0.3. AGENTS.md has the common
names; this file has the rest. Imports: `from stario import App, Context, Files, Relay, Route,
Writer, classes, h`, `from stario.datastar import SSE, at, data, read_signals`,
`from stario.markup import HtmlElement, SafeString, baked`.

## Markup

- `h.HtmlDocument(...)` writes `<!doctype html>`; `h.Html` does not. Void tags (`h.Input`,
  `h.Img`, `h.Br`, `h.Meta`) take attributes only.
- Attribute values: `str`, `int`, `float`, `True` (bare attribute), `False`/`None` (left out).
  `{"class": "a b"}` or `classes("a", {"b": cond})`; `{"style": "..."}`.
- Children: `str` (escaped), numbers, elements, `None` (nothing), lists, `SafeString`. A `bool`
  child raises: write `"yes" if x else "no"`.
- `SafeString(html)` sends HTML as is: never user text. User Markdown carries raw HTML, so
  render it with HTML off (`uv add markdown-it-py`, `MarkdownIt("commonmark", {"html": False})
  .render(text)`) and wrap only that output.
- `@baked` returns a `SafeString`. Every parameter must appear as a child or a whole attribute
  value; no `if`, `==`, f-string or loop on one. Defaults are allowed.
- An SVG icon: `from stario.markup import svg`, `svg.Svg({"viewBox": "0 0 24 24"}, svg.Path({"d": d}))`.

## Datastar attributes (`data.*`)

- `data.signals({...}, if_missing=True)` keeps values a stream already set. Nested:
  `{"form.title": ""}` is `$form.title`. Lists and dicts are allowed values.
- `data.computed("total", "$a + $b")`, `data.effect("expr")` (runs when its signals change),
  `data.ref("box")` (`$box` is the element), `data.json_signals()` (debug).
- `data.on(event, expr, ..., prevent=True, stop=True, once=True, debounce="300ms",
  throttle="1s", delay="200ms", window=True | document=True | outside=True)`. Keys:
  `data.on("keydown", "evt.key === 'Escape' && ($open = false)", window=True)`.
- `data.on_intersect(expr, once=True, threshold=0.5)`, `data.on_interval(expr, duration="5s")`,
  `data.on_signal_patch(expr)`.
- `data.bind("x")` on an input, select, textarea, checkbox (a boolean), radio group (shared
  name); `data.bind("files")` on a file input gives a list of `FileSignal` (base64).
- `data.class_("active", expr)`, `data.classes({"a": expr})`, `data.attr("href", expr)`,
  `data.attrs({...})`, `data.style("width", "$pct + '%'")`, `data.text`, `data.show`.
- `data.indicator("saving")`: `$saving` is true while the element's request runs; put it on the
  element whose `data.on` sends it (a form, not its button).
- `data.ignore_morph()`: a repaint leaves this element alone. `data.preserve_attr("open")`:
  a repaint keeps that attribute (every `h.Dialog` needs it; the page check says so).
- Datastar Pro only, not in the bundled file: `persist`, `query_string`, `replace_url`,
  `scroll_into_view`, `animate`, `custom_validity`, `on_resize`, `on_raf`, `match_media`,
  `view_transition`, `at.clipboard`.

## Actions (`at.*`)

- `at.get/post/put/patch/delete(url, **options)` send every signal not starting with `_` (JSON
  body, or `?datastar=` on GET and DELETE). Options: `include="title|url"` or `exclude=...`
  (regex on names), `content_type="form"` with `selector="#f"` (send a form as a form),
  `headers={...}`, `payload="{id: $x}"` (one JS expression) or
  `payload=literal({"title": title})` (data, also user text).
- Expressions: `@post('/x')` is what `at.post("/x")` returns. Several statements are several
  arguments: `data.on("click", "$busy = true", at.post(SAVE.href()))`.
- `literal(v)` (`stario.datastar`): a Python value as a JS literal in an expression.

## SSE answers (`SSE(w)`)

- `patch_elements(el, mode=...)`: `outer` (default, morph by id), `inner`, `replace`,
  `prepend`, `append`, `before`, `after`; `selector="#list"` targets another element.
  `el` may be a list of elements.
- `patch_signals({...})`, `remove("#id")`, `navigate(url)`, `replace_url(url)`,
  `execute_script(code)` (trusted code), `ping()`, `open()` (headers before the first event).
- One answer may hold several events: patch the list, then clear the form signals.

## Recipes

- Edit dialog that survives repaints: keep `h.Dialog({"id": "edit"}, data.preserve_attr("open"),
  data.attr("open", "$editing"), ...)` outside the repainted element; the typed text lives in
  signals, so a repaint does not lose it.
- Infinite scroll: the last item of the list is a sentinel
  `h.Li({"id": "more"}, data.on_intersect(at.get(MORE.href(query={"page": n + 1})), once=True))`;
  the handler answers `sse.patch_elements(items, mode="append", selector="#list")` and then
  `sse.patch_elements(...)` with the next sentinel, or `sse.remove("#more")` at the end.
- A live count in the navbar on every page (a header badge): the header holds
  `h.Span({"id": "badge"}, data.init(at.get(BADGE_LIVE.href())), str(n))`. Its stream is not behind
  `session.require`: signed out, it patches the empty badge and returns; signed in, it watches
  `SELECT count(*) FROM alerts WHERE user_id = :u AND seen = 0` and patches the whole span each
  time. Build the badge in the page handler too (`page()` takes the header as a parameter).
  Pages with their own stream keep it: one element, one stream.

- A stream whose row was deleted meanwhile (its read returns None) returns: the tab keeps what
  it shows until the next load. A stream never navigates.

## Server

- `Route("GET //{sub}.example.com/")` routes by host. `Route("POST", BASE + "/send")` joins.
- `app.add(R, handler, middleware=[mw])` wraps one route; `app.use(prefix, mw1, mw2)` a prefix.
  A middleware: `def mw(inner: Handler) -> Handler` (`from stario import Handler`), returning
  `async def handler(c, w)`.
- `c.state` is a per-request dict for middleware results. `c.app.create_task(coro)` runs work
  that shutdown waits for. `c.disconnected` says the client left.
- Errors: `raise RedirectException(303, url)` from a helper; `catch_errors(MyError,
  respond=fn)` (`stario.http`, `async def fn(c, w, exc: BaseException)`) turns an exception
  into an answer; `app.not_found("/", handler)`
  is the 404 page; an uncaught exception answers 500 and lands in the trace.
- Uploads: `with await read_form(c.req, max_size=10_000_000) as form:` then `f = form.file("photo")`;
  `f.filename`, `f.content_type`, `await f.read()`. Serve user files with
  `Files(dir, "/uploads", untrusted=True)`.
- Signed cookie: `SignedCookie("prefs", keys=[config.secret])` (`stario.cookies`, keys 32+ bytes);
  `.set(w, {...})`, `.get(c.req)` (a `SignedValue` with `.data`, or None), `.delete(w)`.
  `delete_cookie(w, name)` for a plain one.
- JSON endpoint: `w.json({"items": [...]}, 201)`; read a JSON body with
  `loads(await c.req.body())` and check its shape.
- `security_headers(hsts=31536000)` adds HSTS; `same_origin()` refuses cross-site posts (403).
- Env: `STARIO_HOST`, `STARIO_PORT`, `STARIO_THREADS`, `STARIO_REQUESTS_MAX_BODY_BYTES`,
  `STARIO_GRACEFUL_SHUTDOWN_TIMEOUT`, `STARIO_TRACER=json` (one JSON line per request).

## litewriter

- `await db.aquery(...)` / `aone` / `avalue`: a read on a worker thread, for a heavy query.
- `with db.snapshot():` several reads that see one state (no `await` inside).
- `tx.executemany(sql, [{...}, ...])`; `db.push(fn, ...)` writes without waiting.
- JSON in a column: `TEXT CHECK (json_valid(data))`, read with `data->>'name'`; write
  `dumps(value)` from `stario.json`.
- `IN` a list: `WHERE id IN (SELECT value FROM json_each(:ids))` with `ids=dumps(ids)`.
- Dates: store ISO text (`datetime('now')`, or `datetime.now(UTC).isoformat()`); sort as text.
- A row in, a row out: `db.query(sql, Row)` builds `Row(*columns)` in SELECT order.
