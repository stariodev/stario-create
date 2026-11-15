# A table of `id` plus a JSON document

An optional style for a table whose fields change often. Plain columns stay the default.
The table holds a key and one JSON document. A field that a query filters, sorts, joins,
or keeps unique becomes a virtual column, computed from `data`, with an index. A real
column is for a key the table is about: `id`, `user_id`, `room_id`.

```python
# app/data.py
from stario.json import dumps

NOTE_COLUMNS = {
    "title": "TEXT AS (data->>'title')",
    "done": "INTEGER AS (data->>'done')",
}


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS notes ("
        " id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
    )
    have = {row[0] for row in tx.query("SELECT name FROM pragma_table_xinfo('notes')")}
    for name, column in NOTE_COLUMNS.items():
        if name not in have:
            tx.execute(f"ALTER TABLE notes ADD COLUMN {name} {column} VIRTUAL")
    tx.execute("CREATE INDEX IF NOT EXISTS notes_done ON notes(done)")


def add_note(tx: Tx, title: str) -> int:
    data = dumps({"title": title, "done": False})
    return tx.value("INSERT INTO notes (data) VALUES (:data) RETURNING id", data=data)


def set_note_title(tx: Tx, note_id: int, title: str) -> None:
    tx.execute(
        "UPDATE notes SET data = json_set(data, '$.title', :title) WHERE id = :id",
        id=note_id,
        title=title,
    )
```

- A new field needs no migration: the code writes it into `data`, and old rows read it as `NULL`.
- A new filter or sort is one entry in the columns dict and one index; SQLite computes a virtual column, so no row is rewritten.
- `->>` returns SQL values: a JSON `true` reads as `1`. Type the dataclass field as `int`.
- A JSON literal goes through `json(...)` as a direct argument: `json_set(data, '$.done', json('true'))`.
- An f-string may paste only a constant of the same file (a column name from the dict), never an outside value.
