---
name: stario-accounts
description: Accounts past the add auth kits in a Stario app - Google or GitHub sign-in setup, a signed-in header, rows each user owns, profiles and settings, password change, roles and admin pages, API tokens. Use when the task goes past sign-up, sign-in and protected pages (AGENTS.md has those).
---

# Accounts past the kit

Run the kit right after `new`: `add auth --password` (email and password) or `add auth` (Google
and GitHub). Both write `app/auth/session.py` (`Session`, `current_user`, `local_path`),
`app/auth/data.py` (the `users` table, `get_user`) and `app/pages/login.py`, and put
`session.attach` on every route. The user id is an `int` with `--password` and a `str` with
`add auth`. Read those files instead of rewriting them.

## Google and GitHub (`add auth`)

The kit prints these steps; the app refuses to start without them:

- `.env`: `SESSION_SECRET` (32+ random characters), and `GOOGLE_CLIENT_ID` with
  `GOOGLE_CLIENT_SECRET`, or the `GITHUB_` pair. `APP_DEV=1` on a laptop (plain HTTP).
- Register the callback at each provider: `https://<host>/login/<provider>/callback`, and
  `http://127.0.0.1:8000/login/<provider>/callback` for the laptop.
- `LOGIN_ALLOWED_EMAILS=a@x.com,b@x.com` limits who may sign in.
- `tests/conftest.py` fakes both providers: tests sign in with `login(client, "ada@example.com")`.

## A signed-in header on every page

`page()` is `@baked`, so it cannot branch on the user. Build the header per request and give
`page()` a parameter for it; every page passes it, from `show` and from any stream that repaints
the whole page.

```python
# app/layout.py (add)
from app.auth.data import User
from app.urls import LOGIN, LOGOUT


def header(user: User | None) -> HtmlElement:
    if user is None:
        return h.Nav({"id": "nav"}, h.A({"href": LOGIN.href()}, "Sign in"))
    return h.Nav(
        {"id": "nav"},
        h.Span(user.username),
        h.Form({"method": "post", "action": LOGOUT.href()}, h.Button("Sign out")),
    )
```

```python
@baked
def page(title: str, nav: HtmlElement, body: HtmlElement) -> HtmlElement:
    return h.HtmlDocument(h.Head(h.Title(title)), h.Body(nav, body))
```

In a handler: `user_id = current_user(c)`, then
`nav = header(get_user(self.db, user_id) if user_id is not None else None)`.

## Rows each user owns

A table gets `user_id INTEGER NOT NULL REFERENCES users(id)`. Every read and write of a user's
rows names the owner in its `WHERE`, so another user's row behaves as a missing one:

```python
# app/data.py (add)
def rename_bookmark(tx: Tx, bookmark_id: int, user_id: int, title: str) -> bool:
    """False when the row is missing or belongs to someone else: the handler answers 404."""
    row = tx.one(
        "UPDATE bookmarks SET title = :title WHERE id = :id AND user_id = :user RETURNING id",
        id=bookmark_id,
        user=user_id,
        title=title,
    )
    return row is not None
```

Show an edit or delete button only to the owner, and check again in the handler.

## Profile, settings, password change

User columns (bio, image URL, display name) go in `CREATE TABLE users` in `app/auth/data.py`
(a database with rows: skill `stario-migrate`). Settings is a plain form behind
`session.require`; a taken username or email raises `apsw.ConstraintError` from the write.
A password change checks and hashes before the write:

```python
from app.auth.data import get_login
from app.auth.password import check_password, hash_password

user = get_user(db, signed_in_user(c))
login = get_login(db, user.email) if user else None
form = await read_form(c.req)
if login and await asyncio.to_thread(check_password, form.get("old", ""), login.hash):
    hashed = await asyncio.to_thread(hash_password, form.get("new", ""))
```

Then `await db.write(set_hash, login.id, hashed)` with an `UPDATE users SET hash = ...`.

## Roles and admin pages

A `role TEXT NOT NULL DEFAULT 'user'` column, and middleware that answers 404 to anyone else:

```python
# app/auth/admin.py
from litewriter import LiteWriter
from stario import Context, Handler, Middleware, Writer

from app.auth.session import current_user


def require_admin(db: LiteWriter) -> Middleware:
    def middleware(inner: Handler) -> Handler:
        async def handler(c: Context, w: Writer) -> None:
            user = current_user(c)
            role = db.one("SELECT role FROM users WHERE id = :id", id=user) if user else None
            if role is None or role[0] != "admin":
                w.text("not found", 404)
                return
            await inner(c, w)

        return handler

    return middleware
```

`app.use("/admin", session.require, require_admin(db))` in `app/main.py`.

## API tokens

For scripts that call the app: a table `tokens (hash TEXT PRIMARY KEY, user_id ...)`. Create a
token with `secrets.token_urlsafe(32)`, show it once, store `hashlib.sha256(token.encode())
.hexdigest()`. A middleware on the API prefix reads `c.req.headers.get("authorization")`, strips
`Bearer `, looks the hash up, and answers `w.json({"error": "unauthorized"}, 401)` when it is
unknown. Keep cookie routes and token routes on different prefixes.
