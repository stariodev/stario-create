from dataclasses import dataclass

from litewriter import LiteWriter, Tx
from stario.json import dumps

from app.common.providers import Identity
from app.common.providers.github import GITHUB
from app.common.providers.google import GOOGLE

# The issuers whose verified email may join an existing user. Each one proves that
# the person owns the address. Add your own issuer only when its users cannot set
# any email they like; else a user there could take over a Google account.
LINK_BY_EMAIL = frozenset({GOOGLE, GITHUB})


@dataclass(frozen=True, slots=True)
class User:
    id: str
    email: str
    name: str


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id TEXT PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
    )
    # email: the verified email from an issuer in LINK_BY_EMAIL, else ''. Joins use only it.
    tx.execute(
        "CREATE TABLE IF NOT EXISTS identities ("
        " issuer TEXT NOT NULL, subject TEXT NOT NULL,"
        " user_id TEXT NOT NULL REFERENCES users(id),"
        " email TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (issuer, subject))"
    )
    tx.execute("CREATE INDEX IF NOT EXISTS identities_email ON identities(email) WHERE email != ''")


def get_user(db: LiteWriter, user_id: str) -> User | None:
    return db.one(
        "SELECT id, coalesce(data->>'email', ''), coalesce(data->>'name', '')"
        " FROM users WHERE id = :id",
        User,
        id=user_id,
    )


def add_login(tx: Tx, who: Identity, new_id: str) -> str:
    """The user id of `who`. A new identity joins the user that has an identity with
    the same linkable email; else it is a new user."""
    linkable = who.email if who.email_verified and who.issuer in LINK_BY_EMAIL else ""
    row = tx.one(
        "SELECT user_id FROM identities WHERE issuer = :issuer AND subject = :subject",
        issuer=who.issuer,
        subject=who.subject,
    )
    if row is None and linkable:
        row = tx.one("SELECT user_id FROM identities WHERE email = :email LIMIT 1", email=linkable)
    user_id = row[0] if row is not None else new_id
    if row is None:
        tx.execute("INSERT INTO users (id, data) VALUES (:id, '{}')", id=user_id)
    tx.execute(
        "INSERT INTO identities (issuer, subject, user_id, email)"
        " VALUES (:issuer, :subject, :user_id, :email)"
        " ON CONFLICT (issuer, subject) DO UPDATE SET email = excluded.email",
        issuer=who.issuer,
        subject=who.subject,
        user_id=user_id,
        email=linkable,
    )
    # Display fields only. An empty or unverified value never replaces a good one.
    shown = {"email": who.email if who.email_verified else "", "name": who.name}
    if fields := {k: v for k, v in shown.items() if v}:
        tx.execute(
            "UPDATE users SET data = json_patch(data, :data) WHERE id = :id",
            data=dumps(fields),
            id=user_id,
        )
    return user_id
