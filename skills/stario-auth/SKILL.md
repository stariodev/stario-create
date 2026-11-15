---
name: stario-auth
description: Accounts in a Stario app - the session cookie, password sign-in, Google and GitHub sign-in (`stario-create add auth`), protected pages, per-user rows, admin pages, API tokens.
---

# Accounts

Sign-in goes through a provider: `uvx stario-create@latest add auth` (below). Build password sign-in only when the developer or the spec asks for it; then write the missing parts (email check, reset, rate limit) in `## This app`.

Both ways share one session: a `SignedCookie` that holds the user id and an expiry, signed. It holds no profile, no password, no role. Handlers never read the cookie: they call `current_user(c)`. Logout is a `POST`. A redirect to a `next` value goes through `local_path`, so it stays on this site.

## Password sign-in

```python
# app/auth.py
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from stario import Context, Handler, RedirectException, Writer
from stario.cookies import SignedCookie

_USER = "user"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${key.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, _, key = stored.partition("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(got.hex(), key)


def current_user(c: Context) -> int | None:
    """The signed-in user id, or None. Needs session.attach on the route."""
    return c.state.get(_USER)


def require_user(c: Context, login_url: str = "/login") -> int:
    """The user id; a signed-out request goes to the login page."""
    user = current_user(c)
    if user is None:
        raise RedirectException(303, login_url)
    return user


@dataclass(frozen=True, slots=True)
class Session:
    cookie: SignedCookie

    def issue(self, w: Writer, user_id: int) -> None:
        self.cookie.set(w, {_USER: user_id})

    def clear(self, w: Writer) -> None:
        self.cookie.delete(w)

    def attach(self, inner: Handler) -> Handler:
        async def handler(c: Context, w: Writer) -> None:
            value = self.cookie.get(c.req)
            user = value.data.get(_USER) if value is not None else None
            c.state[_USER] = user if type(user) is int else None
            await inner(c, w)

        return handler
```

In `bootstrap`, after `same_origin()` and `security_headers()`:

```python
session = Session(SignedCookie("__Host-session", keys=[config.session_secret]))
app.use("/", session.attach)
LoginPage(db, session).register(app)
```

`session_secret` is a `Config` field: 32+ random characters from the env. With none set (a laptop, a test), make one once and keep it in `config.data_dir / "session.key"`.

The commands, in `app/pages/login.py` (routes in `app/urls.py`, `add_user` and `get_login` in `app/data.py`). Hash outside the write, in a thread, since scrypt takes about 50 ms:

```python
async def sign_up(self, c: Context, w: Writer) -> None:
    signals = await read_signals(c.req)
    name = str(signals.get("username", "")).strip()
    email = str(signals.get("email", "")).strip().lower()
    password = str(signals.get("password", ""))
    if not name or "@" not in email or len(password) < 8:
        SSE(w).patch_signals({"_error": "username, email and an 8+ character password"})
        return
    hashed = await asyncio.to_thread(hash_password, password)
    try:
        user_id = await self.db.write(add_user, name, email, hashed)
    except apsw.ConstraintError:
        SSE(w).patch_signals({"_error": "that username or email is taken"})
        return
    self.session.issue(w, user_id)
    SSE(w).navigate(HOME.href())


async def sign_in(self, c: Context, w: Writer) -> None:
    signals = await read_signals(c.req)
    login = get_login(self.db, str(signals.get("email", "")).strip().lower())
    password = str(signals.get("password", ""))
    if login is None or not await asyncio.to_thread(check_password, password, login.hash):
        SSE(w).patch_signals({"_error": "email or password is invalid"})
        return
    self.session.issue(w, login.id)
    SSE(w).navigate(HOME.href())
```

Set the cookie before `SSE(w)` sends its first event. A plain `<form method="post">` reads `read_form` and answers `w.redirect(url, status=303)` instead. Tests: `await client.post(SIGN_UP.href(), json={...})`; the client keeps the cookie, so the next request is signed in.

## Sign-in with providers

`uvx stario-create@latest add auth` adds `litewriter` and writes tested files: `app/auth/providers/` (`Google` on the OIDC code in `oidc.py`, `GitHub` on OAuth 2), `app/auth/session.py` (`Session` with `attach` and `require`, `current_user(c)`, `local_path`), `app/auth/data.py` (the `users` and `identities` tables, `get_user`), `app/pages/login.py` (`GET /login`, `POST /login/{provider}`, its callback, `POST /logout`; the routes go at the end of `app/urls.py`), `app/config.py`, and `tests/test_login.py` with `login(client, email=..., provider=...)` against `FakeProviders`. A file the app changed is kept: the command prints `merge by hand: <file>`.

Then create an OAuth client at each provider and register `https://<host>/login/<provider>/callback` (and `http://127.0.0.1:8000/...` for the laptop). Put `SESSION_SECRET`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (or the `GITHUB_` pair), and `APP_DEV=1` in `.env`; on Yard, `yard env edit --app <name>` without `APP_DEV`. `LOGIN_ALLOWED_EMAILS` (comma-separated) limits who may sign in.

- A user is keyed by `identities(issuer, subject)`, never by the email. A new identity joins the user with the same verified email only for issuers in `LINK_BY_EMAIL`.
- Another OIDC issuer (Pocket ID, Rauthy, for passkeys) subclasses `OidcIssuer` like `google.py`. Keep every token check in `OidcIssuer`.

## Protect pages

- Pages under a prefix: `app.use("/app", session.require)` (kit) covers each route below it. One route: `app.add(ROUTE, handler, middleware=[session.require])`. In a handler: `user = require_user(c)`.
- A signed-out page load gets a 303 to the login page; a signed-out Datastar request gets `navigate`.
- Order in `bootstrap`: `same_origin()`, `security_headers()`, then `session.attach`, then any `require`.

## Rows that belong to a user

A per-user table has a real `user_id` column with an index. Every read, stream, and command filters by `current_user(c)`. A command checks that the row belongs to the user before it changes it: a row of another user gets 404, never 403. A test signs in two users and checks that each sees only its own rows.

## Admin pages and API tokens

- An admin is a signed-in user whose email is in `ADMIN_EMAILS` (a `Config` field). A middleware method on `/admin`, after `require`, answers 404 to anyone else.
- An API token: `"<app>_" + secrets.token_urlsafe(32)`, shown once; store only its SHA-256 with `user_id`, `name`, `created`, `used`. A middleware on the API prefix reads `Authorization: Bearer <token>`; no row gets 401. Never put a token in a URL.
