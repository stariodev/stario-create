---
name: stario-auth
description: Accounts in a Stario app - password sign-up and sign-in (add auth --password), Google or GitHub sign-in (add auth), logout, protected pages, rows per user, API tokens. Use for any login, register, or permission need.
---

# Accounts

Never write sign-in by hand: a kit writes tested files. Run one at the app root, right after `new` and before you edit any file:

```bash
uvx stario-create@latest add auth --password   # email and password: sign-up, sign-in, logout
uvx stario-create@latest add auth              # Google and GitHub through OAuth
```

A kit replaces only files still equal to the scaffold; a changed file is kept, and the command prints `merge by hand: <file>` with the path of the kit version. Both kits share one session: a `SignedCookie` that holds the user id, signed, with an expiry. It holds no profile, no password, no role. Handlers never read the cookie: they call `current_user(c)`.

## `add auth --password`

- `app/auth/session.py`: `Session` with `issue`, `clear`, and the middleware `attach` and `require`; `current_user(c) -> int | None`; `signed_in_user(c) -> int` behind `require`; `local_path(url)` keeps a `next` URL on this site.
- `app/auth/password.py`: `hash_password`, `check_password` (scrypt, about 50 ms: the page calls them through `asyncio.to_thread`, outside the write).
- `app/auth/data.py`: the `users` table (`id`, `email`, `username`, `hash`, `created`; unique email and username, any case), `get_user(db, id) -> User | None`, `get_login`, `add_user`.
- `app/pages/login.py`: `GET /login` and `GET /signup` (Datastar forms with `_error`), `POST /login`, `POST /signup`, `POST /logout`. A sign-in sets the cookie, then answers `navigate` to `next` or home. The routes go at the end of `app/urls.py`: `LOGIN`, `SIGN_IN`, `SIGNUP`, `SIGN_UP`, `LOGOUT`.
- `app/config.py`: `session_secret` from `SESSION_SECRET`; unset, a random key kept in `data/session.key`. `APP_DEV=1` drops `Secure` for plain HTTP on a host other than localhost.
- `tests/test_login.py`: sign-up, sign-in, a wrong password, a taken email, logout, a protected page.

More fields at sign-up (a bio, an image): add the columns to the `CREATE TABLE users` in `app/auth/data.py` (a new app has no old rows), to `add_user`, and to the form. A task's own URLs (`/register`): change the routes in `app/urls.py`; the page class keeps them. A task whose forms post plain HTML (`<form method="post">`) or use its own field names: keep `session.py` and `password.py`, and rewrite `app/pages/login.py` and `tests/test_login.py` together in one step.

## `add auth` (providers)

It writes `app/auth/providers/` (`Google` on OIDC, `GitHub` on OAuth 2), the same session with string user ids, `app/auth/data.py` (`users` and `identities`), `app/pages/login.py`, and `tests/test_login.py` against `FakeProviders`. Then create an OAuth client at each provider and register `https://<host>/login/<provider>/callback` (and `http://127.0.0.1:8000/...` for the laptop); put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (or the `GITHUB_` pair), `SESSION_SECRET`, and `APP_DEV=1` in `.env`. Another issuer, the email allow list, and linking by email: `references/providers.md`.

## Protect pages

- Pages under a prefix: `app.use("/editor", session.require)` in `bootstrap`, after `session.attach`. One route: `app.add(ROUTE, handler, middleware=[session.require])`. A handler behind it reads `user_id = signed_in_user(c)`.
- A page for everyone that shows more when signed in reads `current_user(c)`, which is `None` for a visitor.
- A signed-out page load gets a 303 to the login page and comes back after it; a signed-out Datastar action gets `navigate`.
- Sign out is a plain form anywhere: `h.Form({"method": "post", "action": LOGOUT.href()}, h.Button("Sign out"))`.

## Rows that belong to a user

A per-user table has a real `user_id` column with an index. Every read, stream, and command filters by the signed-in user. A command checks that the row belongs to the user before it changes it: a row of another user gets 404, never 403. A test signs up two users (`client.cookies.clear()` between them) and checks that each sees only its own rows.

Admin pages and API tokens: `references/admin-and-tokens.md`.
