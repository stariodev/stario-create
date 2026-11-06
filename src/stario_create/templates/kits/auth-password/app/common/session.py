import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

from stario import Context, Handler, Writer
from stario.cookies import SignedCookie
from stario.datastar import SSE

_USER = "user"


def current_user(c: Context) -> str | None:
    """The signed-in user id of this request, or None. Needs Session.attach."""
    if _USER not in c.state:
        raise RuntimeError("current_user() needs the session.attach middleware on this route")
    return c.state[_USER]


def local_path(url: object, default: str = "/") -> str:
    """`url` when it is a path on this site, else `default`. Stops an open redirect."""
    if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
        return default
    return default if "\\" in url else url


@dataclass(frozen=True, slots=True)
class Session:
    """Built once in bootstrap. attach and require are middleware: register
    the bound methods, session.attach and session.require."""

    cookie: SignedCookie
    login_url: str

    def issue(self, w: Writer, user_id: str) -> None:
        self.cookie.set(w, {_USER: user_id})

    def clear(self, w: Writer) -> None:
        self.cookie.delete(w)

    def attach(self, inner: Handler) -> Handler:
        """Every request below it: current_user(c) is the user id or None. A visit past
        half of max_age sets the cookie again, so an active user stays signed in."""

        async def handler(c: Context, w: Writer) -> None:
            value = self.cookie.get(c.req)
            user = value.data.get(_USER) if value is not None else None
            c.state[_USER] = user if isinstance(user, str) else None
            if value is not None and c.state[_USER] and value.age > self.cookie.max_age / 2:
                self.cookie.set(w, value.data)
            await inner(c, w)

        return handler

    def require(self, inner: Handler) -> Handler:
        """A page for signed-in users. A page load goes to the login page and
        comes back after it. A Datastar action navigates to the login page."""

        async def handler(c: Context, w: Writer) -> None:
            if current_user(c) is None:
                if c.req.headers.get("datastar-request"):
                    SSE(w).navigate(self.login_url)
                else:
                    target = c.req.raw_path.decode()
                    if c.req.query_bytes:
                        target += "?" + c.req.query_bytes.decode("utf-8", "replace")
                    w.redirect(f"{self.login_url}?{urlencode({'next': target})}", status=303)
                return
            await inner(c, w)

        return handler


def hash_password(password: str, salt: bytes | None = None) -> str:
    """About 30 ms of CPU. Call it through asyncio.to_thread from a handler.
    The text has no `$` or `,`, so it fits in an env file."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{_b64(salt)}.{_b64(digest)}"


def check_password(password: str, stored: str) -> bool:
    salt, _, _ = stored.partition(".")
    try:
        raw = base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4))
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, raw), stored)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


@dataclass(slots=True)
class Tries:
    """Failed logins for each account, in memory. `limit` failures inside
    `window` seconds lock that account until the oldest one is older."""

    limit: int = 5
    window: float = 900
    failed: dict[str, list[float]] = field(default_factory=dict[str, list[float]])

    def locked(self, email: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self.failed.get(email, []) if now - t < self.window]
        self.failed[email] = recent
        return len(recent) >= self.limit

    def fail(self, email: str) -> None:
        self.failed.setdefault(email, []).append(time.monotonic())

    def clear(self, email: str) -> None:
        self.failed.pop(email, None)
