# Admin pages and API tokens

## Admin pages

An admin is a signed-in user whose email is in `ADMIN_EMAILS` (a `Config` field, comma-separated). A middleware method on `/admin`, after `session.require`, answers 404 to anyone else, so the admin pages do not show that they exist:

```python
# app/auth/admin.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import Context, Handler, Writer

from app.auth.data import get_user
from app.auth.session import signed_in_user


@dataclass(frozen=True, slots=True)
class Admins:
    db: LiteWriter
    emails: frozenset[str]

    def require(self, inner: Handler) -> Handler:
        async def handler(c: Context, w: Writer) -> None:
            user = get_user(self.db, signed_in_user(c))
            if user is None or user.email.lower() not in self.emails:
                w.text("not found", status=404)
                return
            await inner(c, w)

        return handler
```

In `bootstrap`: `app.use("/admin", session.require, Admins(db, config.admin_emails).require)`.

## API tokens

- A token is `"<app>_" + secrets.token_urlsafe(32)`, shown to the user once. Store only its SHA-256, with `user_id`, `name`, `created`, and `used`.
- A middleware on the API prefix reads `Authorization: Bearer <token>`, hashes it, and finds the row; no row gets 401. It sets the user for `current_user(c)` like `session.attach` does.
- Never put a token in a URL: it lands in logs and in the browser history.
- A test creates a token, calls the API with the header, deletes the token, and gets 401.
