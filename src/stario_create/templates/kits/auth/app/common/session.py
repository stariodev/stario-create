import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from stario import Context, Handler, Writer
from stario.cookies import SignedCookie
from stario.datastar import SSE

_USER = "user"


def current_user(c: Context) -> str | None:
    """The signed-in user id of this request, or None. Needs Session.attach."""
    if _USER not in c.state:
        raise RuntimeError("current_user() needs the session.attach middleware on this route")
    return c.state[_USER]


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

    def user_id(self, c: Context) -> str | None:
        value = self.cookie.get(c.req)
        user = value.data.get(_USER) if value is not None else None
        return user if isinstance(user, str) else None

    def attach(self, inner: Handler) -> Handler:
        """Every request below it: current_user(c) is the user id or None."""

        async def handler(c: Context, w: Writer) -> None:
            c.state[_USER] = self.user_id(c)
            await inner(c, w)

        return handler

    def require(self, inner: Handler) -> Handler:
        """A page for signed-in users. A page load redirects. A Datastar action navigates."""

        async def handler(c: Context, w: Writer) -> None:
            if current_user(c) is None:
                if c.req.headers.get("datastar-request"):
                    SSE(w).navigate(self.login_url)
                else:
                    w.redirect(self.login_url, status=303)
                return
            await inner(c, w)

        return handler


def hash_password(password: str, salt: bytes | None = None) -> str:
    """About 30 ms of CPU. Call it through asyncio.to_thread from a handler."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def check_password(password: str, stored: str) -> bool:
    salt_b64, _, _ = stored.partition("$")
    return hmac.compare_digest(hash_password(password, base64.b64decode(salt_b64)), stored)
