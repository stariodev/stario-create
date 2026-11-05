# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia. A handler writes HTML. Datastar morphs it into the page. One open SSE response keeps a page live. State lives on the server. Docs: https://stario.dev/docs.

The last section of this file holds the notes of this app, under 4 KB. A deep note on one topic goes in its own file, named by a line such as "Read `EDITOR.md` before you change the editor."

## Which skill

Read the one skill for the task in `.agents/skills/`, then write the code. `stario-create add <kit>` writes tested files.

- A static page (no command): no skill. Write `urls.py`, `views.py`, and a page class with one `show`.
- A page that every tab sees change, in SQLite: `stario-feature` and `stario-litewriter`.
- State in memory, a message to one tab, an edit dialog: `stario-relay`.
- A sort, a filter, paging, a search as you type: `stario-view`.
- Work that takes seconds, or a loop on a timer: `stario-jobs`.
- Login: `stario-auth`. Styles: `stario-tailwind-daisyui`. JavaScript: `stario-client`.
- Before a browser or a screenshot: `stario-browser-check`.
- `stario-api` lists every signature. Read it only for a name that the skill and the code do not show.

## Layout

```text
app/
  main.py           bootstrap: shared objects, one register line per page under `# pages`
  config.py         Config: one field with a default per setting; from_env reads it by name
  common/shell.py   page(title, body): the <html> document
  features/<page>/  urls.py (Routes, the View), views.py (render), handlers.py (the page class), data.py (SQL)
  <name>/           code with no URL; never imports features/
tests/test_<page>.py
```

- A page is one folder, named after the URL noun: `/rooms/{room_id}` → `room`. It gets one line in `LINKS` in `app/features/home/views.py`.
- A feature may import the `urls.py` and `data.py` of another feature, never its views or handlers.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string.

## Stario rules

- Not ASGI: no Uvicorn, FastAPI, or response objects.
- `bootstrap(app, span)` is an async generator with one `yield`. Keep `app.use("/", same_origin(), security_headers())`. `same_origin()` is the CSRF guard: add no CSRF tokens. It does not check GET, so a GET never changes state.
- A handler is `async def (c: Context, w: Writer) -> None`. It answers once: `w.html`, `w.text`, `w.empty`, `w.redirect`, or `SSE(w)`.
- `Route("GET /rooms/{room_id}")` is one method on one path. `app.add(ROUTE, handler)`; `ROUTE.href(room_id, query={...})`. No `url_for`.
- A stream loop iterates `c.alive(source)`. Background work is `c.app.create_task(coro)`. A timer loop waits on `app.shutdown`, never `asyncio.sleep`.
- No module-level state. No `os.environ` outside `config.py`. JSON goes through `stario.json`.

## A page is a resource

- **Go somewhere** (a page, a sort, a filter): `<a href>`. The query holds the view.
- **A result only this tab needs** (search as you type): a `GET` that answers `SSE(w).patch_elements(part)`.
- **Change state**: a command, `POST`.

A page on state that cannot change while it is open is static: `w.html(render(...))`. A page on shared state is live:

```text
GET  /board        the document; its top element has data.init(at.get(BOARD_LIVE.href(), retry="always"))
GET  /board/live   the stream: send render(...), and again after each change
POST /board/...    a command
```

The stream is the only thing that sends HTML. It follows `db.watch(query)` (SQLite) or `relay.subscribe(CHANGED, latest=True)` (memory). A command never answers with HTML:

1. Read: `await read_signals(c.req)`, `c.match.params`.
2. Validate: bad input gets `w.text("why", status=400)` and `return`.
3. Reply: `w.empty()`, `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)`.
4. Execute: `await db.write(...)`, or change memory, then `relay.publish(CHANGED, {})`.

## Render and signals

- `render(...)` returns the whole document from state. It does not fetch.
- The element with `data.init(...)` and `data.signals({...}, if_missing=True)` keeps its tag, `id`, and attributes in every render.
- Signals carry what the user types or picks. A leading `_` keeps a signal in the tab. One signal per field, not one per row.
- A busy form: `data.indicator("_saving")` on the `<form>`, `data.attr("disabled", "$_saving")` on its button.
- A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.

## Code shape

A page is one class in `handlers.py`. Its fields are its dependencies. A read or a write is a function in `data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`.

```python
@dataclass(frozen=True, slots=True)
class BoardPage:
    db: LiteWriter
    relay: Relay[dict]

    def register(self, app: App) -> None:
        app.add(BOARD, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        view = BoardView.from_query(c.req.query)
        w.html(render(list_tiles(self.db, view), view))
```

No service classes, repositories, base pages, `utils`, or helpers with one call site. Read input like this:

```python
title = str(signals.get("title", "")).strip()  # text
done = signals.get("done") is True  # bool
tile_id = c.match.params["tile_id"]  # path int: tile_id.isdecimal(), then int(tile_id)
```

## Tests

Tests run `TestClient(bootstrap, request_timeout=5)`. Each page: it loads, a command repaints the stream, bad input gets 4xx. The next SSE event is the changed HTML; two streams are two tabs. A `GET` sends signals in `params={"datastar": '{"q": "x"}'}`, a `POST` in `json=`. `tests/test_pages.py` finds and checks every page by itself.

A bug starts with a test that shows it. Run `just test -k <name>` and see it fail. Then fix, see it pass, and read `git diff`.

## Checks

Change a file with the Edit tool. Run Python as `uv run python`. Run `just check` after each change: it formats, fixes lint, checks types, runs the tests, and prints only problems. pyrefly checks each call, so trust Stario, Datastar, and litewriter.

A browser is only for client JS that holds state. No computer use. When the user watches the app, the user is the browser: say what to look at. When it does not work: `curl` their server, then a failing test (skill `stario-browser-check`).

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

## This app

Notes for this app go below. `stario-create sync` replaces the text above and keeps this section.
