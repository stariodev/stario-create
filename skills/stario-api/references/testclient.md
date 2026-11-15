# TestClient

`tests/conftest.py` of a new app gives the `client` fixture: `TestClient(bootstrap)` on an
empty data dir (`PROJECT_DATA_DIR=tmp_path`). Write tests only when the task has no
acceptance suite: each page gets one test file (it loads, a command repaints the stream,
bad input is refused); a bug starts with a test that shows it. Skill `stario-feature`
has a whole test file for a page.

```text
r = await client.get(url, params={"datastar": '{"q": "x"}'})   # a GET with signals
r = await client.post(url, json={"title": "milk"})       # a Datastar action
r = await client.post(url, data={"email": "a@b.c"})      # a plain form, urlencoded
r = await client.post(url, files={"photo": ("a.png", b"...", "image/png")})
r = await client.get(url, follow_redirects=False)        # r.headers.get("location")
r.status_code  r.text  r.json()  r.url (a str)  r.headers.get(name)  r.cookies
async with client.stream("GET", LIVE.href(), timeout=2) as live:
    events = live.iter_events()            # dicts with "event" and "data"
    first = (await anext(events))["data"]
await client.drain_tasks(timeout=1)        # waits for every create_task task, a forever loop too
client.tracer.find_span("report.run")      # TelemetrySpan | None: assert it is not None
```

- Read the first stream event before the command, so the subscription is up; the next event is the repaint. Two streams are two tabs. `timeout=2` fails a missing repaint in two seconds.
- Buffered calls follow redirects; `stream` does not. A `navigate` answer contains `window.location`.
- The client keeps cookies in `client.cookies` (a dict): `client.cookies.clear()` signs out, and saving and restoring it switches users.
- A test of the app with other settings: `monkeypatch.setenv("REPORT_DELAY", "0")` before `TestClient(bootstrap)`; `Config.from_env` reads it.
- `tests/test_pages.py` already checks every page that a link reaches (routes, signals, ids, dialogs, the stream's element). A test with rows calls `assert not await check(client, url)` from it.
