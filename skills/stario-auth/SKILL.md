---
name: stario-auth
description: Accounts in a Stario app - sign-in with Google, GitHub, or any OpenID Connect issuer, a signed session cookie, protected pages, rows that belong to one user, and closed password accounts for an admin page. Use when the user asks for login, sign-in, accounts, sessions, "who is the user", per-user data, an allow list, or a page only some users can open. The code comes from `stario-create add auth` or `add auth-password`; this skill says which kit, how to wire it, and what not to change.
---

# Accounts

Do not write sign-in or the session by hand. Pick the kit:

| The app | Kit |
| --- | --- |
| Any app with users: public, paid, private, or a family tool | `add auth`: sign-in with Google, GitHub, or an OIDC issuer. The default. |
| One admin page, or a tool for a few known people, with no issuer | `add auth-password`: closed accounts from the env. |

Do not build open sign-up with an email and a password. It needs an email check, a password reset, a rate limit, and a check for leaked passwords. The provider already does all of them. When the developer asks for password sign-up, say this and offer `add auth`. Build it only when they insist, and list the missing parts in `## This app`.

## Sign-in with providers

Run the kit in the root of the app:

```bash
uvx stario-create@latest add auth
```

It adds `litewriter` and writes tested files:

| File | What it holds |
| --- | --- |
| `app/common/providers.py` | `Issuer` (Google or any OIDC issuer) and `GitHub`. Each is a `Provider`: `authorize_url` and `identity`. `Flow`: state, nonce, PKCE. `Http`: the calls, which tests replace. |
| `app/common/session.py` | `Session`: the signed cookie, `attach`, `require`. `current_user(c)`. `local_path(url)`. |
| `app/features/login/` | `GET /login`, `POST /login/{provider}`, `GET /login/{provider}/callback`, `POST /logout`, the button text in `views.py` (`LABELS`), and in `data.py` the `users` and `identities` tables, `get_user`, and `LINK_BY_EMAIL`. |
| `app/config.py` | One client pair for each provider, `login_allowed_emails`, `session_secret`, `app_dev`. |
| `tests/conftest.py`, `tests/test_login.py` | `FakeProviders`, a `login(client, email=..., provider=...)` helper, and the tests. |

A file that the app has changed is not replaced. The command prints `merge by hand: <file>` and the path of the kit version. Read that file and merge its lines into yours.

Then:

1. Create an OAuth client at each provider. Google: Google Auth Platform, Clients, Web application. GitHub: Settings, Developer settings, OAuth Apps.
2. Register the callback for each host: `https://<host>/login/<provider>/callback`, and `http://127.0.0.1:8000/login/<provider>/callback` for the laptop. Open the app at that same host: `just dev` prints `http://127.0.0.1:8000`.
3. Put `SESSION_SECRET` (32+ random characters), the client pairs, and `APP_DEV=1` in `.env`. On Yard: `yard env edit --app <name>`, with no `APP_DEV`.
4. Run `just check`.

The env. A provider is on when both of its values are set, and the app needs at least one:

| Variables | Provider |
| --- | --- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google, as `/login/google`. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub, as `/login/github`. |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Any other OIDC issuer with discovery (Rauthy, Pocket ID, Keycloak, GitLab), as `/login/oidc`. Write its button text in `LABELS`. |
| `LOGIN_ALLOWED_EMAILS` | Comma-separated verified emails that may sign in. Empty: every account. |

Rules for this kit:

- `app/main.py` builds `providers: dict[str, Provider]`. The key is the name in the route. The login page shows one button for each key, with the text from `LABELS`. The flow cookie holds the name, so a callback cannot switch providers.
- Another provider that is not OIDC (Facebook, Discord): write a class with `authorize_url` and `identity`, like `GitHub`, add it to the dict, and add its text to `LABELS`. Or use an issuer that brokers it, such as Rauthy.
- The key of a user is `identities(issuer, subject)` to `users.id`. Never key a user, a row, or a session on the email: an email can change.
- A new identity joins the user with the same verified email, but only when both come from an issuer in `LINK_BY_EMAIL` (Google and GitHub). Thus one user can sign in with both. Add your own issuer there only when its users cannot set any email they like.
- `Issuer` checks that discovery names the configured issuer, that the endpoints are HTTPS, and `iss`, `aud`, `azp`, `exp`, and `nonce` in the ID token. Keep each check. Never decode an ID token anywhere else.
- The callback URL comes from the request host. Register every host of the app at each provider.
- "Signed in as": `get_user(db, current_user(c))` gives `id`, `email`, and `name`. Sign out is a plain form that posts to `LOGOUT.href()`.
- An allow list from the database (invited emails, project members): replace the `self.allowed` check in `callback` with a query.
- Test a sign-in with `await login(client, email="bob@example.com", provider="github")`. It runs the real routes against `FakeProviders`.

## Closed password accounts

```bash
uvx stario-create@latest add auth-password
```

It writes `app/common/session.py` (with `hash_password`, `check_password`, and `Tries`), `app/features/login/`, the config, the tests, and a `just password-hash` recipe. It has no sign-up page and no users table.

- The accounts live in `LOGIN_ACCOUNTS`: `email:hash,email:hash`. `just password-hash ada@example.com` asks for the password and prints one entry.
- To add, remove, or reset an account, edit `LOGIN_ACCOUNTS` and restart the app.
- The user id is the email.
- Five wrong passwords in 15 minutes lock that account. Thus anyone can lock an account for 15 minutes, and "Too many tries" shows that the account exists. Both are acceptable for a few known accounts.
- An unknown email still runs one hash, so the answer time does not show which accounts exist.
- Use it for an admin page or a few known people only. An app with more users uses `add auth`.

## Protect pages

Both kits protect pages in the same way:

- A new app keeps its protected pages under `/app`. One `app.use("/app", session.require)` covers each route below it, and its 404 and 405 answers too.
- An app that already has pages keeps its URLs. Protect each page where it is: `app.use("/todos", session.require)`. Then set `PROTECTED` in `tests/test_login.py` to `/todos`.
- One protected route outside a prefix: `app.add(ROUTE, handler, middleware=[session.require])`.
- A signed-out page load gets a 303 to `/login?next=<path and query>`, and the sign-in comes back there. A signed-out Datastar request gets `navigate`.
- In `app/main.py`, the order matters: `same_origin()` and `security_headers()` come before `session.attach`, and `attach` comes before any `require`.

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
- Rows from before accounts: ask the developer whether they go to the first user or away. If you cannot ask, keep them and write the open choice in `## This app`.

## Rules

- The cookie holds the user id and an expiry, signed. It holds no profile, no password, no role, no row.
- `httponly=True` always. `secure=True` outside local development. `samesite="lax"`, so the callback from the provider carries the flow cookie.
- A protected page uses `require`. A handler never reads the cookie itself. It calls `current_user(c)`.
- A redirect to a `next` value goes through `local_path`, so it stays on this site.
- Logout is a `POST`.
- A session lasts `max_age` (14 days), and each visit past half of it starts a new `max_age`. It cannot be revoked one at a time, and the allow list is checked only at sign-in. To end sessions, add a `session_version` to the user `data` and to the cookie, and compare them in `Session.attach`.
- Prove sign-in with `TestClient`. The client keeps cookies. Do not open a browser for a sign-in or a redirect.
