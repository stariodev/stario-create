from dataclasses import dataclass
from datetime import UTC, datetime

from litewriter import LiteWriter, Tx


@dataclass(frozen=True, slots=True)
class User:
    id: int
    email: str
    username: str


@dataclass(frozen=True, slots=True)
class Login:
    id: int
    hash: str


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id INTEGER PRIMARY KEY, email TEXT NOT NULL, username TEXT NOT NULL,"
        " hash TEXT NOT NULL, created TEXT NOT NULL)"
    )
    # A taken email or username raises apsw.ConstraintError in add_user.
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(lower(email))")
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username ON users(lower(username))")


def get_user(db: LiteWriter, user_id: int) -> User | None:
    return db.one("SELECT id, email, username FROM users WHERE id = :id", User, id=user_id)


def get_login(db: LiteWriter, email: str) -> Login | None:
    return db.one(
        "SELECT id, hash FROM users WHERE lower(email) = lower(:email)", Login, email=email
    )


def add_user(tx: Tx, email: str, username: str, hashed: str) -> int:
    return tx.value(
        "INSERT INTO users (email, username, hash, created)"
        " VALUES (:email, :username, :hash, :created) RETURNING id",
        email=email,
        username=username,
        hash=hashed,
        created=datetime.now(UTC).isoformat(),
    )
