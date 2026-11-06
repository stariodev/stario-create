from litewriter import Tx
from stario.json import dumps

from app.common.oidc import Identity


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id TEXT PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)),"
        " email TEXT AS (data->>'email') VIRTUAL)"
    )
    tx.execute("CREATE INDEX IF NOT EXISTS users_email ON users(email)")
    tx.execute(
        "CREATE TABLE IF NOT EXISTS identities ("
        " issuer TEXT NOT NULL, subject TEXT NOT NULL,"
        " user_id TEXT NOT NULL REFERENCES users(id),"
        " PRIMARY KEY (issuer, subject))"
    )


def add_login(tx: Tx, who: Identity, new_id: str) -> str:
    """The user id of `who`. A new identity joins the user with the same
    verified email, so a new issuer keeps the old accounts. Else it is a new user."""
    data = dumps({"email": who.email, "name": who.name})
    row = tx.one(
        "SELECT user_id FROM identities WHERE issuer = :issuer AND subject = :subject",
        issuer=who.issuer,
        subject=who.subject,
    )
    if row is not None:
        tx.execute(
            "UPDATE users SET data = json_patch(data, :data) WHERE id = :id", data=data, id=row[0]
        )
        return row[0]
    row = None
    if who.email_verified and who.email:
        row = tx.one("SELECT id FROM users WHERE email = :email LIMIT 1", email=who.email)
    user_id = row[0] if row is not None else new_id
    if row is None:
        tx.execute("INSERT INTO users (id, data) VALUES (:id, :data)", id=user_id, data=data)
    tx.execute(
        "INSERT INTO identities (issuer, subject, user_id) VALUES (:issuer, :subject, :user_id)",
        issuer=who.issuer,
        subject=who.subject,
        user_id=user_id,
    )
    return user_id
