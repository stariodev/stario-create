import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from stario import Context, Handler, Writer
from stario.cookies import delete_cookie, set_cookie
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

    secret: bytes
    login_url: str
    cookie: str = "session"
    max_age: int = 60 * 60 * 24 * 14
    secure: bool = True

    def sign(self, body: str) -> str:
        digest = hmac.new(self.secret, body.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode()

    def issue(self, w: Writer, user_id: str) -> None:
        body = f"{user_id}.{int(time.time()) + self.max_age}"
        set_cookie(
            w,
            self.cookie,
            f"{body}.{self.sign(body)}",
            max_age=self.max_age,
            httponly=True,
            secure=self.secure,
            samesite="lax",
        )

    def clear(self, w: Writer) -> None:
        delete_cookie(w, self.cookie, httponly=True, secure=self.secure, samesite="lax")

    def user_id(self, c: Context) -> str | None:
        body, _, sig = c.req.cookies.get(self.cookie, "").rpartition(".")
        user_id, _, exp = body.rpartition(".")
        if not user_id or not exp.isdecimal() or int(exp) < time.time():
            return None
        return user_id if hmac.compare_digest(self.sign(body), sig) else None

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
