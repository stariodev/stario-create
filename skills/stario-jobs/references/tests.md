# Tests for jobs and loops

## A job runs to done

The `client` fixture in `tests/conftest.py` gets `monkeypatch.setenv("REPORT_DELAY", "0")`.

```python
# tests/test_reports.py
from app.urls import REPORTS_LIVE, START_REPORT


async def test_a_job_runs_to_done(client):
    async with client.stream("GET", REPORTS_LIVE.href(), timeout=2) as live:
        events = live.iter_events()
        await anext(events)
        assert (await client.post(START_REPORT.href())).status_code == 204
        async for event in events:
            if "done" in event["data"]:
                break
    await client.drain_tasks(timeout=1)  # a timer loop never ends: give a timeout
    span = client.tracer.find_span("report.run")
    assert span is not None and span.ok
```

The test reads events until one contains `done`. `timeout=2` covers the whole stream, so it must be longer than the delay of the job.

## Loops stop on shutdown

The `server.shutdown` span gets one `server.shutdown.task_cancelled` event, with `task.name`, for each task that the drain cancels (stario 5.3.2). Give the loop a `name`. A test checks that the loop stops in time:

```python
# tests/test_shutdown.py
from stario.testing import TestClient

from app.main import bootstrap


async def test_loops_stop_on_shutdown():
    async with TestClient(bootstrap) as client:
        pass
    shutdown = client.tracer.find_span("server.shutdown")
    assert shutdown is not None
    assert not client.tracer.get_events(shutdown.id, name="server.shutdown.task_cancelled")
```

