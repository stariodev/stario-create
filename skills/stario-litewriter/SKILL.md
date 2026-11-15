---
name: stario-litewriter
description: Change a SQLite table that already holds rows - upgrade at start, a new column with its old rows filled, indexes, unique values, JSON columns, how watch wakes. Use when the schema of a filled database changes or a watch does not repaint.
---

# SQLite with litewriter

One SQLite file, one writer thread, reads from any thread. `watch` wakes a stream after a commit changes the rows it reads. Verified against litewriter 0.3 (`uv add "litewriter>=0.3.3,<0.4"`, or `new --db`).

```text
async with LiteWriter(config.db_path, schema=schema, claim=30) as db:   # in bootstrap
db.query(sql, Row, **params)    # list of Row(*columns); without Row, tuples
db.one(sql, Row, **params)      # Row or None
db.value(sql, **params)         # the first column of the first row; raises when there is none
await db.write(fn, *args)       # fn(tx, *args) in one transaction; returns fn's value
db.push(fn, *args)              # fire and forget; a failure goes to the litewriter logger
db.submit(fn, *args).result()   # the same write from a plain thread (on the loop it raises)
await db.aquery(sql, Row)       # aquery, aone, avalue: on a worker thread
async with db.watch(sql, Row, **params) as rows:   # the rows now, then after each change
    async for items in c.alive(rows): ...
tx.execute(sql, **params)  tx.query  tx.one  tx.value  tx.last_insert_rowid()
apsw.ConstraintError            # a taken unique value; LiteError is the base of the rest
```

`claim=30` makes a second process wait 30 seconds, then raise `ClaimBusy`. On dev reload, run the watcher so the app is its direct child (`just dev`); a `ClaimBusy` in dev is an orphan: `lsof <db>.sqlite3-claim`, then kill that PID.

## Upgrade a table that holds rows

`schema` runs at every start, on a file the last version of the app filled. Each change checks first, so the next start changes nothing:

```python
# app/data.py
def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS articles ("
        " id INTEGER PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL)"
    )
    have = {row[0] for row in tx.query("SELECT name FROM pragma_table_xinfo('articles')")}
    if "published" not in have:
        tx.execute("ALTER TABLE articles ADD COLUMN published TEXT")
        tx.execute("UPDATE articles SET published = created")  # the old rows: published then
    tx.execute("CREATE INDEX IF NOT EXISTS articles_published ON articles(published)")
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS articles_title ON articles(lower(title))")
```

- Set the old rows in the same step as the `ALTER`, and only there: a later start must not touch them. A `NOT NULL` column needs a `DEFAULT`.
- Never drop, rename, or recreate a table that holds rows. A column of another type is a new column, filled from the old one. A column no query uses: `DROP INDEX`, then `ALTER TABLE ... DROP COLUMN`, once, behind the same check.
- `pragma_table_xinfo` lists virtual columns too; `pragma_table_info` does not.
- A test writes a file with the old `schema` and rows, starts the app on it twice, and checks the rows.
- A table of `id` plus one JSON document, with virtual columns for the fields a query uses: `references/json-tables.md`.

## Writes

A write is a plain `def` whose first argument is `tx`, in `app/data.py`. The writer runs it in one transaction, in its own savepoint, and commits in a batch; you do not commit.

- It holds the whole batch: no network, no sleep, no password hash. Related changes go in one function.
- Read inside it with `tx.query`, `tx.one`, `tx.value`, never `db.query`. Do not keep `tx`.
- A command validates, awaits the write (up to 1/60 s), then replies, so a taken unique value (`apsw.ConstraintError`) goes back in the reply as `_error`.
- `db.push` returns before the commit, so a read soon after can miss the row: push only a counter or a last-seen stamp.

## The stream: `watch`

- The first iteration gives the rows now; each later one comes after a commit that writes a table and a column that the query reads. Equal rows do not wake. A slow stream gets the newest rows, not a backlog.
- A new field that the query does not select repaints nothing: add it to the query.
- Values are parameters: `db.watch(SQL, Todo, most=0)`. `ORDER BY` and column names cannot be parameters: keep one fixed SQL text per sort key (skill `stario-view`).
- Only commits through this `LiteWriter` wake a watch; a write from another process does not.
- Rows plus a message to one tab: the stream also subscribes to a `Relay` (skill `stario-relay`).

## Rules

- One `LiteWriter` per file per process. `IF NOT EXISTS` on every `CREATE`.
- `tests/conftest.py` points `PROJECT_DATA_DIR` at `tmp_path`, so each test gets its own file.
