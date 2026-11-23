---
name: stario-migrate
description: Change SQLite tables that already hold rows in a Stario app - add a column and fill old rows, rename or retype one, an index, a test on an old database. Use when a table with rows gets a new or changed column (an app in use, an upgrade). Not for new tables, which CREATE TABLE IF NOT EXISTS makes.
---

# Change tables that hold rows

`schema(tx)` in `app/data.py` runs at every start, in one transaction, before the app serves.
`CREATE TABLE IF NOT EXISTS` never changes a table that exists. So each change is a step that
looks at the file first and does nothing when it already ran: the second start changes nothing,
and the old rows stay. Never drop or recreate a table that holds rows.

```python
# app/data.py (add)
def columns(tx: Tx, table: str) -> set[str]:
    return {row[0] for row in tx.query("SELECT name FROM pragma_table_info(:t)", t=table)}


def upgrade_bookmarks(tx: Tx) -> None:
    """Call this at the end of schema(tx)."""
    have = columns(tx, "bookmarks")
    if "pinned" not in have:
        # Old rows get the default. NOT NULL needs a DEFAULT on ADD COLUMN.
        tx.execute("ALTER TABLE bookmarks ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    if "updated" not in have:
        # ADD COLUMN takes only a constant default: add it empty, then fill the old rows once.
        tx.execute("ALTER TABLE bookmarks ADD COLUMN updated TEXT NOT NULL DEFAULT ''")
        tx.execute("UPDATE bookmarks SET updated = created WHERE updated = ''")
    tx.execute("CREATE INDEX IF NOT EXISTS bookmarks_pinned ON bookmarks(pinned, id)")
```

Then use the column everywhere it shows: select it into the row dataclass, write it in the
write functions, and add it to the query a stream watches (`CHANGES`), or a live page will not
repaint when it changes.

## Rules

- Put new columns in the `CREATE TABLE` too, so a new database gets them at once; the `ALTER`
  step then sees the column and does nothing.
- A new table is `CREATE TABLE IF NOT EXISTS`: it starts empty, so events from before the
  upgrade make no rows in it (no old notifications, no old activity).
- Old rows that must count as something (every old post is published, with its first date):
  add the column, then one `UPDATE ... WHERE <column> IS NULL` inside the same `if`.
- A value only the app can compute (a slug from a title, a hash): read the rows in the step,
  compute in Python, `tx.execute("UPDATE ...", ...)` per row. No network call in `schema`.
- Rename or change the type of a column, or drop a constraint: rebuild once, guarded by the
  column check. `CREATE TABLE new_t (...)`, `INSERT INTO new_t (cols) SELECT cols FROM t`,
  `DROP TABLE t`, `ALTER TABLE new_t RENAME TO t`, then the indexes again. Keep the ids.
- Sessions and caches may be dropped; user rows, passwords and dates may not.
- `DATABASE_PATH`, when set, is the file the app opens (the scaffold's `Config.db_path`).

## Test it on an old database

Make a file with the old schema and rows, start the app on it twice, and check the rows:

```python
# tests/test_upgrade.py
import apsw
from stario.testing import TestClient

from app.main import bootstrap
from app.urls import BOOKMARKS


async def test_an_old_database_keeps_its_rows(tmp_path, monkeypatch):
    old = apsw.Connection(str(tmp_path / "app.sqlite3"))
    old.execute(
        "CREATE TABLE bookmarks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,"
        " created TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO bookmarks (title, url) VALUES ('Old one', 'https://old.example')"
    )
    old.close()
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    for _ in range(2):  # the second start must change nothing
        async with TestClient(bootstrap) as client:
            assert "Old one" in (await client.get(BOOKMARKS.href())).text
```

A copy of a real database works the same way: `DATABASE_PATH=/tmp/copy.sqlite3` and
`uv run python -m app.main`, or copy it to `tmp_path / "app.sqlite3"` in a test.
