"""The tables, their rows, and every read and write: a read takes `db`, a write takes `tx`."""

from dataclasses import dataclass

from litewriter import LiteWriter, Tx

PAGE_SIZE = 10
TODOS_PAGE = "SELECT id, title FROM todos ORDER BY id DESC LIMIT :limit OFFSET :offset"


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    title: str


def schema(tx: Tx) -> None:  # runs at every start: IF NOT EXISTS on every CREATE
    tx.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")


def list_todos(db: LiteWriter, page: int) -> list[Todo]:
    return db.query(TODOS_PAGE, Todo, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)


def add_todo(tx: Tx, title: str) -> int:
    return tx.value("INSERT INTO todos (title) VALUES (:title) RETURNING id", title=title)
