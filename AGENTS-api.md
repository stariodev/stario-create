# Stario API guide

How to build a Stario JSON API. This is the default; when the developer asks for something else, do that. App notes live in `## This app` at the end.

Stario is a Python HTTP framework. This app has no HTML and no Datastar. A handler reads the request and writes JSON or text. Docs: https://stario.dev/docs.

Before you call work done, run `just check` (ruff, ruff format, pyrefly, pytest) and fix every failure.

## Stario rules

- Not ASGI: no Uvicorn, FastAPI, or response objects. The main module runs `asyncio.run(serve(bootstrap))`.
- `bootstrap(app: App, span: Span)` is an async generator with one `yield`: build shared objects, register routes, `yield`, clean up. Routes are fixed after `bootstrap`.
- A handler is `async def handler(c: Context, w: Writer) -> None`. It answers once: `w.json`, `w.text`, `w.empty`, or `w.redirect`.
- `Route("GET /apps/{name}")` is one method on one path. `app.add(ROUTE, handler)` registers it; `ROUTE.href(name)` builds the path. No `url_for`, no `app.get`.
- A literal segment beats a parameter, in any order: `/rooms/live` and `/rooms/{room_id}` both work.
- `c.match.params`, `c.req.query`, `c.req.cookies`; `c.state` is filled by middleware. Middleware is `(inner: Handler) -> Handler`, added with `app.use("/prefix", mw)`.
- A long loop iterates `c.alive(source)`. Background work is `c.app.create_task(coro)`, never bare `asyncio.create_task`. A timer loop reads `shutdown = app.shutdown` once, then ends each pass with `await asyncio.wait({shutdown}, timeout=interval)`, never `asyncio.sleep`, so it stops at once on shutdown.
- JSON goes through `stario.json` (`w.json`), not `json.dumps`.
- One process, one event loop. Shared state is an object built in `bootstrap` and passed to the code that registers routes. No module-level state. No `os.environ` outside the config module.
- Stario does not read `.env`. Settings come from the environment; `set dotenv-load := true` in the `justfile` loads a local `.env`.

## Requests

- Validate every input. Malformed or forged input gets `w.text("why", status=400)` (or 404, 403, 409) and `return`.
- In a handler: read input, validate (4xx and `return`), do the work, reply.
- Slow work (a build, a download, a model call) runs in `c.app.create_task(self.run(job, c.span.step("job.run")))`. The handler records the job and replies. The task works inside `with span:`, updates the job status, and marks the job failed on `CancelledError` (Stario cancels it at shutdown). A client reads that status from another route.
- A delay, a timeout, or an external client is a config field, so tests run fast and use fakes.

## Storage

Choose with the developer. Do not add a database the app does not need.

- No persistence: an object built in `bootstrap`.
- SQLite: litewriter is the recommended default. Plain `sqlite3` is fine for a small app.
- Every `SCHEMA` statement is `IF NOT EXISTS`.
- Files live in `config.data_dir`: `$PROJECT_DATA_DIR`, or `./data` on a laptop. Yard sets `/data`, which survives every deploy. The database is `config.db_path` there. Tests set `PROJECT_DATA_DIR` to `tmp_path`.

## Code shape

- Routes that share dependencies live in one class: a frozen dataclass whose fields are the dependencies, `register(app)` adds the routes, and each route is one method (`app.add(APP, self.show)`). No handler factories.
- Code that wraps one external tool (a CLI, a socket, an HTTP API) is an adapter. Tests replace it with a fake.
- Queries and service methods are named by verb: `list_*`, `get_*` (one or `None`), `add_*`, `set_*`, `remove_*`.
- Fewer, fuller functions. Inline a function with one call site. No compatibility aliases, no comments that repeat the code.

## Tests

Tests run the production `bootstrap` through `TestClient`. Each route: a good request returns the expected status and body; malformed input returns 400. A service test builds the service with fake adapters. That is the proof. Do not open a browser.

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`. Prove a change with `TestClient`. Do not use computer use.

## This app

Notes for this app go below. `stario-create sync` replaces the text above and keeps this section.
