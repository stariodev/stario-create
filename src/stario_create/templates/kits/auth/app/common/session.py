from dataclasses import dataclass
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
        """A page for signed-in users. A page load goes to the login page and
        comes back after it. A Datastar action navigates to the login page."""

        async def handler(c: Context, w: Writer) -> None:
            if current_user(c) is None:
                if c.req.headers.get("datastar-request"):
                    SSE(w).navigate(self.login_url)
                else:
                    w.redirect(f"{self.login_url}?{urlencode({'next': c.req.path})}", status=303)
                return
            await inner(c, w)

        return handler
