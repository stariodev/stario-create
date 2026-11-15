# Jobs in SQLite

A job row in SQLite outlives the process. A row stays `running` when the process stops. The schema function marks these rows when the app starts, so a restart leaves no job stuck:

```python
# app/data.py, inside schema(tx), after the CREATE TABLE of jobs
tx.execute(
    "UPDATE jobs SET status = 'failed', result = 'interrupted'"
    " WHERE status IN ('queued', 'running')"
)
```

The stream then follows `db.watch` on the jobs table (skill `stario-litewriter`), and `run` writes each status with `await db.write(...)` in place of the publish.
