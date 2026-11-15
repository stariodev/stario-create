# Sign-in with providers (`add auth`)

- `LOGIN_ALLOWED_EMAILS` (comma-separated) limits who may sign in. Empty: every account of the providers.
- On Yard: `yard env edit --app <name>` with the client pairs and `SESSION_SECRET`, without `APP_DEV`.
- A user is keyed by `identities(issuer, subject)`, never by the email. A new identity joins the user with the same verified email only for issuers in `LINK_BY_EMAIL` (`app/auth/data.py`). Add an issuer there only when its users cannot set any email they like; else a user there could take over a Google account.
- Another OIDC issuer (Pocket ID, Rauthy, for passkeys) subclasses `OidcIssuer` like `app/auth/providers/google.py`. Keep every token check in `OidcIssuer`.
- Each provider is on when its client pair is set (`app/main.py`); its name is the `<provider>` in `/login/<provider>`.
- Tests sign in with `login(client, email=..., provider=...)` from `tests/conftest.py`. An email that starts with `unverified+` comes back unverified; GitHub refuses a code for an email that starts with `refuse+`.
