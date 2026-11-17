---
name: stario-jobs
description: Slow work in a Stario app (a report, a model call, an import) as a job with live progress and clean shutdown, and a loop on a timer. Use when a command starts work that takes seconds, or work runs on a schedule.
---

# Slow work as a job

The page is a live page on a `Relay` (skill `stario-relay`): the command queues a job and replies at once. A task does the work inside its own span and publishes each status change. The `queued` row is the click feedback.

```python
# app/data.py
from dataclasses import dataclass, field
from itertools import count


@dataclass(slots=True)
class Job:
    id: int
    status: str = "queued"  # queued | running | done | failed
    result: str = ""


@dataclass(slots=True)
class Jobs:
    rows: dict[int, Job] = field(default_factory=dict)
    ids: count[int] = field(default_factory=lambda: count(1))


def add_job(jobs: Jobs) -> Job:
    job = Job(next(jobs.ids))
    jobs.rows[job.id] = job
    return job


def list_jobs(jobs: Jobs) -> list[Job]:
    return sorted(jobs.rows.values(), key=lambda j: j.id, reverse=True)
```

```python
# app/urls.py
REPORTS = Route("GET /reports")
REPORTS_LIVE = Route("GET /reports/live")
START_REPORT = Route("POST /reports")
```

```python
# app/pages/reports.py
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from stario import App, Context, Relay, Span, Writer, h
from stario.datastar import SSE, at, data
from stario.markup import HtmlElement

from app.data import Job, Jobs, add_job, list_jobs
from app.layout import page
from app.urls import REPORTS, REPORTS_LIVE, START_REPORT

CHANGED = "reports.changed"


@dataclass(frozen=True, slots=True)
class ReportsPage:
    jobs: Jobs
    relay: Relay[dict]
    delay: float

    def register(self, app: App) -> None:
        app.add(REPORTS, self.show)
        app.add(REPORTS_LIVE, self.live)
        app.add(START_REPORT, self.start)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(list_jobs(self.jobs)))

    async def live(self, c: Context, w: Writer) -> None:
        async with self.relay.subscribe(CHANGED, latest=True) as events:
            sse = SSE(w)
            sse.patch_elements(render(list_jobs(self.jobs)))
            async for _ in c.alive(events):
                sse.patch_elements(render(list_jobs(self.jobs)))

    async def start(self, c: Context, w: Writer) -> None:
        job = add_job(self.jobs)
        self.relay.publish(CHANGED, {})
        c.app.create_task(self.run(job, c.span.step("report.run")))
        w.empty()

    async def run(self, job: Job, span: Span) -> None:
        with span:
            span.attrs({"job.id": job.id})
            job.status = "running"
            self.relay.publish(CHANGED, {})
            try:
                await asyncio.sleep(self.delay)  # the slow work
                job.result, job.status = f"Report at {datetime.now(UTC):%H:%M:%S}", "done"
            except asyncio.CancelledError:
                job.result, job.status = "stopped: the server shut down", "failed"
                raise
            except Exception as exc:
                job.result, job.status = str(exc), "failed"
                span.fail(str(exc))
            finally:
                self.relay.publish(CHANGED, {})


def render(jobs: list[Job]) -> HtmlElement:
    return page(
        "Reports",
        h.Main(
            {"id": "reports"},
            data.init(at.get(REPORTS_LIVE.href(), retry="always")),
            h.Button(
                {"type": "button"},
                data.on("click", at.post(START_REPORT.href())),
                data.indicator("_starting"),
                data.attr("disabled", "$_starting"),
                "Generate report",
            ),
            h.Ul(*[h.Li({"id": f"job-{j.id}"}, f"#{j.id} {j.status} {j.result}") for j in jobs]),
        ),
    )
```

The button carries `data.indicator` because its own `data.on` sends the request.

```python
# app/main.py, inside bootstrap before yield
jobs = Jobs()
ReportsPage(jobs, relay, config.report_delay).register(app)
```

`report_delay: float = 5.0` is a `Config` field; `from_env` reads `REPORT_DELAY`. A test sets it to `0`.

- `c.span.step("report.run")` is a child of the request span. The task enters it with `with span:`, so the job has its own duration, events, and error in the trace.
- `c.app.create_task`, never bare `asyncio.create_task`. Stario tracks the task and waits for it on shutdown.
- An error goes to the job row and to the span. Nothing is lost when the request has already ended.
- On shutdown, Stario waits `STARIO_GRACEFUL_SHUTDOWN_TIMEOUT` (5 s), then cancels the task. `CancelledError` marks the job failed and is raised again.
- A job with several steps passes `c.app` to `run`, checks `app.shutting_down` between the steps, and stops early.
- Several jobs run at once: each click is its own task.
- A message to the tab that started the job (a toast when it fails): skill `stario-relay`, A message to one tab.

## A loop on a timer

Work that runs every few seconds or minutes with no click: a sweep, a poll, a cleanup. `bootstrap` starts the loop. Each pass ends with a wait on `app.shutdown`.

```python
# app/cleanup.py
import asyncio

from stario import App

from app.data import Jobs


async def drop_finished_forever(app: App, jobs: Jobs, interval: float) -> None:
    shutdown = app.shutdown
    while not app.shutting_down:
        for job in list(jobs.rows.values()):
            if job.status in ("done", "failed"):
                del jobs.rows[job.id]
        await asyncio.wait({shutdown}, timeout=interval)
```

```python
# app/main.py, inside bootstrap before yield
app.create_task(drop_finished_forever(app, jobs, 600), name="jobs.drop_finished")
```

- `asyncio.wait` returns after `interval`, or at once when shutdown starts; it does not cancel `app.shutdown`. Read `app.shutdown` once, before the loop: each read returns a new awaitable.
- Never end a pass with `asyncio.sleep(interval)`: the drain then waits up to one interval and, after 5 s, cancels the loop.
- A loop that waits on a queue or an event waits on `shutdown` too: `asyncio.wait({event_wait, shutdown}, timeout=...)`; clear the event after the wait.
- Give the loop a `name`. In a handler, loop on `c.alive()` instead.

## Tests

A job that runs to done, and loops that stop on shutdown: `references/tests.md`.

## Jobs in SQLite

A job row in SQLite outlives the process; `schema` marks the rows a stop left `running`: `references/sqlite-jobs.md`.
