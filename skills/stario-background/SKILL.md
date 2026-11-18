---
name: stario-background
description: State and work outside SQLite in a Stario app - a live page on state in memory (Relay), slow work with live progress (an export, an import, a model call), a timer loop, a message to one tab, clean shutdown. Use when state is not in the database or work outlasts the request.
---

# State in memory, jobs, timers

A live page on SQLite watches a query (AGENTS.md). Without a database, or for progress that is
not a row, a `Relay` carries the news: a command changes the state and publishes; each open
stream receives the message and repaints. Build the state and the relay in bootstrap and pass
them to the page class: module state is refused by the lint and leaks between tests.

## A live page on memory

```python
# app/pages/poll.py
from dataclasses import dataclass, field

from stario import App, Context, Relay, Route, Writer, h
from stario.datastar import SSE, at, data
from stario.markup import HtmlElement

from app.layout import page

POLL = Route("GET /poll")  # routes live in app/urls.py in a real app
POLL_LIVE = Route("GET /poll/live")
VOTE = Route("POST /poll/{option}")


@dataclass(slots=True)
class Votes:
    counts: dict[str, int] = field(default_factory=lambda: {"tea": 0, "coffee": 0})


@dataclass(frozen=True, slots=True)
class PollPage:
    votes: Votes
    relay: Relay[str]

    def register(self, app: App) -> None:
        app.add(POLL, self.show)
        app.add(POLL_LIVE, self.live)
        app.add(VOTE, self.vote)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(page("Poll", render_counts(self.votes)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.relay.subscribe("poll") as messages:  # subscribe, then send the state
            sse.patch_elements(render_counts(self.votes))
            async for _ in c.alive(messages):
                sse.patch_elements(render_counts(self.votes))

    async def vote(self, c: Context, w: Writer) -> None:
        option = c.match.params["option"]
        if option not in self.votes.counts:
            w.text("no such option", 404)
            return
        self.votes.counts[option] += 1
        self.relay.publish("poll", option)
        w.empty()


def render_counts(votes: Votes) -> HtmlElement:
    return h.Ul(
        {"id": "counts"},
        data.init(at.get(POLL_LIVE.href())),
        *[
            h.Li(f"{name}: {n} ", h.Button(data.on("click", at.post(VOTE.href(name))), "Vote"))
            for name, n in votes.counts.items()
        ],
    )
```

In bootstrap: `PollPage(Votes(), Relay()).register(app)`. Subjects are dotted strings:
`publish("room.7", msg)`; `subscribe("room.7")`, `subscribe("room.*")` or `subscribe("*")`.
`subscribe(..., latest=True)` keeps only the newest message per subject for a slow tab.

A message to one tab: the page gives each tab an id, `data.signals({"tab": uuid4().hex})`; the
stream reads it with `read_signals(c.req)` and subscribes to `f"tab.{tab}"`; a command publishes
there.

## A slow job with live progress

A command starts the work and answers at once. `c.app.create_task(...)` runs it, and shutdown
waits for it (never `asyncio.create_task`: the lint refuses it). Blocking work goes through
`await asyncio.to_thread(fn, ...)`. Progress travels on the relay; the result goes to the
database or to a file under `config.data_dir`.

```python
# app/pages/export.py
import asyncio
from dataclasses import dataclass, field

from stario import App, Context, Relay, Route, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

EXPORT = Route("POST /export")
EXPORT_LIVE = Route("GET /export/live")
EXPORT_FILE = Route("GET /export/{job}/export.csv")


@dataclass(slots=True)
class Jobs:
    percent: dict[str, int] = field(default_factory=dict)  # job id -> percent done


@dataclass(frozen=True, slots=True)
class ExportPage:
    jobs: Jobs
    relay: Relay[int]

    def register(self, app: App) -> None:
        app.add(EXPORT, self.start)
        app.add(EXPORT_LIVE, self.live)

    async def start(self, c: Context, w: Writer) -> None:
        job = str((await read_signals(c.req)).get("job", ""))
        if not job.isalnum() or job in self.jobs.percent:
            w.text("bad job id", 400)
            return
        self.jobs.percent[job] = 0
        c.app.create_task(self.run(c.app, job))
        w.empty()

    async def run(self, app: App, job: str) -> None:
        for percent in range(10, 101, 10):
            if app.shutting_down:
                return
            await asyncio.to_thread(sum, range(1_000_000))  # one slice of the real work
            self.jobs.percent[job] = percent
            self.relay.publish(f"job.{job}", percent)

    async def live(self, c: Context, w: Writer) -> None:
        job = str((await read_signals(c.req)).get("job", ""))
        sse = SSE(w)
        async with self.relay.subscribe(f"job.{job}") as messages:
            sse.patch_elements(render_job(job, self.jobs.percent.get(job, 0)))
            async for _subject, percent in c.alive(messages):
                sse.patch_elements(render_job(job, percent))


def render_job(job: str, percent: int) -> HtmlElement:
    """The element with data.init: the page and every event send all of it."""
    return h.Div(
        {"id": "job"},
        data.init(at.get(EXPORT_LIVE.href())),
        h.Progress({"max": 100, "value": percent}),
        h.A({"href": EXPORT_FILE.href(job)}, "Download") if percent == 100 else None,
    )
```

The page holds `data.signals({"job": uuid4().hex})`, a button with
`data.on("click", at.post(EXPORT.href()))`, and `render_job(job, 0)`. The download route answers
`w.respond(body, b"text/csv; charset=utf-8")` after
`w.headers.set("content-disposition", 'attachment; filename="export.csv"')`. In a test,
`await client.drain_tasks()` waits for the job.

## A timer loop

Start it in bootstrap, before `yield`: `app.create_task(purge_old(app, db))`. It waits on the
shutdown future, not on `asyncio.sleep`, so the app stops at once:

```python
# app/data.py (add)
import asyncio

from stario import App


def delete_old(tx: Tx) -> None:
    tx.execute("DELETE FROM bookmarks WHERE created < datetime('now', '-30 days')")


async def purge_old(app: App, db: LiteWriter, every: float = 60) -> None:
    shutdown = app.shutdown  # read once, before the loop
    while not app.shutting_down:
        await db.write(delete_old)
        await asyncio.wait({shutdown}, timeout=every)
```

A stream that must send something on a timer (a clock, a keep-alive) does the same inside
`async with c.alive():`.
