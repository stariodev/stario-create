---
name: stario-auth
description: Accounts in a Stario app - sign-up, sign-in, sign-out, a signed session cookie, protected pages, and rows that belong to one user. Use when the user asks for login, accounts, sessions, "who is the user", per-user data, or a page only some users can open. The code comes from `stario-create add auth`; this skill says how to wire it and what not to change.
---

# Accounts

Do not write the session or the login page by hand. Run the kit in the root of the app:

```bash
uvx stario-create@latest add auth
```

It adds `litewriter` and writes tested files:

| File | What it holds |
| --- | --- |
| `app/common/session.py` | `Session(cookie, login_url)`: issue and clear a `SignedCookie`, read its user id. `attach` and `require` are middleware methods. `current_user(c)` is the user id or `None`. `hash_password` and `check_password` (scrypt). |
| `app/features/login/` | `GET /login`, `POST /login`, `POST /logout`, and the `users` table in `data.py`. |
| `app/features/signup/` | `GET /signup` and `POST /signup`. A taken email sets `_error`. |
| `app/config.py` | `session_secret`, `dev`, `admin_email`, `admin_password`. |
| `app/main.py` | The `LiteWriter`, the seed admin, the `SignedCookie` (`__Host-session`, or `session` with `APP_DEV=1`), the middleware, `/app` protected. |
| `tests/conftest.py`, `tests/test_login.py` | Test settings, a `login(client)` helper, and the tests. |

A file that the app has changed is not replaced. The command prints `merge by hand: <file>` and the path of the kit version. Read that file and merge its lines into yours. In `app/main.py`, the order matters: `same_origin()` and `security_headers()` come before `session.attach`, and `attach` comes before any `require`.

Then:

1. Put `SESSION_SECRET` (32+ random characters) and `APP_DEV=1` in `.env`. `just dev` loads it. On Yard: `yard env edit --app <name>`, with no `APP_DEV`.
2. Run `just check`.

## Protect pages

- A new app keeps its protected pages under `/app`. One `app.use("/app", session.require)` covers each route below it, and its 404 and 405 answers too.
- An app that already has pages keeps its URLs. Protect each page where it is: `app.use("/todos", session.require)`. Then set `PROTECTED` in `tests/test_login.py` to `/todos`.
- One protected route outside a prefix: `app.add(ROUTE, handler, middleware=[session.require])`.
- A signed-out page load gets a 303. A signed-out Datastar request (a stream, a command) gets `navigate`.

## Rows that belong to a user

A table of per-user rows gets a real `user_id` column with an index. Add it once in `schema`:

```python
if "user_id" not in have:
    tx.execute("ALTER TABLE todos ADD COLUMN user_id TEXT")
tx.execute("CREATE INDEX IF NOT EXISTS todos_user ON todos(user_id)")
```

- Every read, stream, and command filters by `current_user(c)`: `db.watch("... WHERE user_id = :user ...", Todo, user=user)`.
- A command checks that the row belongs to the user before it changes it. A row of another user gets 404, never 403.
- A test signs in two users and asserts that each stream shows only its own rows.
- Rows from before accounts: ask the developer whether they go to the seed user or away. If you cannot ask, keep them and write the open choice in `## This app`.

## Rules

- The cookie is a `SignedCookie`: the user id, signed, with an expiry that the server checks. It holds no password, no role, no row.
- `httponly=True` always. `secure=True` outside local development. `samesite="lax"`. The name is `__Host-session`, so a subdomain cannot set it.
- To rotate `SESSION_SECRET`, pass `keys=[new, old]` for one `max_age`. Each key is 32 bytes or more.
- A password is hashed with scrypt in `asyncio.to_thread`, never inside a write function. It is never stored in clear, logged, or put in a span attribute.
- A protected page uses `require`. A handler never reads the cookie itself.
- A command that acts for a user reads `current_user(c)`, not a signal or a path parameter.
- Logout is a `POST`.
- A session lasts `max_age` and cannot be revoked one at a time. For "sign out everywhere", add a `session_version` to the user row and to the cookie data, and compare them in `Session.user_id`.
- Prove login with `TestClient`. The client keeps cookies, so `await login(client)` signs in the next requests. Do not open a browser for a sign-in or a redirect.
