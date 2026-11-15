import asyncio
from dataclasses import dataclass

import apsw
from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.auth.data import add_user, get_login
from app.auth.password import check_password, hash_password
from app.auth.session import Session, current_user, local_path
from app.layout import page
from app.urls import HOME, LOGIN, LOGOUT, SIGN_IN, SIGN_UP, SIGNUP

# Sign out is a plain form anywhere: h.Form({"method": "post", "action": LOGOUT.href()}, ...)


@dataclass(frozen=True, slots=True)
class LoginPage:
    db: LiteWriter
    session: Session

    def register(self, app: App) -> None:
        app.add(LOGIN, self.show_login)
        app.add(SIGN_IN, self.sign_in)
        app.add(SIGNUP, self.show_signup)
        app.add(SIGN_UP, self.sign_up)
        app.add(LOGOUT, self.logout)

    async def show_login(self, c: Context, w: Writer) -> None:
        next_url = local_path(c.req.query.get("next", ""), HOME.href())
        if current_user(c) is not None:
            w.redirect(next_url, status=303)
            return
        w.html(render_login(next_url))

    async def show_signup(self, c: Context, w: Writer) -> None:
        next_url = local_path(c.req.query.get("next", ""), HOME.href())
        w.html(render_signup(next_url))

    async def sign_in(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        email = str(signals.get("email", "")).strip()
        password = str(signals.get("password", ""))
        login = get_login(self.db, email)
        # A missing user still costs one hash, so the answer time does not tell.
        stored = login.hash if login is not None else _DUMMY
        if not await asyncio.to_thread(check_password, password, stored) or login is None:
            SSE(w).patch_signals({"_error": "email or password is invalid"})
            return
        self.session.issue(w, login.id)
        SSE(w).navigate(local_path(signals.get("next"), HOME.href()))

    async def sign_up(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        username = str(signals.get("username", "")).strip()
        email = str(signals.get("email", "")).strip()
        password = str(signals.get("password", ""))
        if not 1 <= len(username) <= 40 or "@" not in email or len(email) > 200:
            SSE(w).patch_signals({"_error": "a username and an email are required"})
            return
        if len(password) < 8:
            SSE(w).patch_signals({"_error": "the password needs 8 or more characters"})
            return
        hashed = await asyncio.to_thread(hash_password, password)
        try:
            user_id = await self.db.write(add_user, email, username, hashed)
        except apsw.ConstraintError:
            SSE(w).patch_signals({"_error": "that email or username is taken"})
            return
        self.session.issue(w, user_id)
        SSE(w).navigate(local_path(signals.get("next"), HOME.href()))

    async def logout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        if c.req.headers.get("datastar-request"):
            SSE(w).navigate(LOGIN.href())
        else:
            w.redirect(LOGIN.href(), status=303)


_DUMMY = hash_password("not a password")


def field(label: str, name: str, kind: str = "text") -> HtmlElement:
    return h.Label(label, h.Input({"type": kind, "name": name, "required": True}, data.bind(name)))


def render_login(next_url: str) -> HtmlElement:
    return page(
        "Sign in",
        h.Main(
            {"id": "login"},
            data.signals({"email": "", "password": "", "next": next_url, "_error": ""}),
            h.H1("Sign in"),
            h.Form(
                data.on("submit", at.post(SIGN_IN.href()), prevent=True),
                field("Email", "email", "email"),
                field("Password", "password", "password"),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
                h.Button({"type": "submit"}, "Sign in"),
            ),
            h.P(h.A({"href": SIGNUP.href(query={"next": next_url})}, "Need an account?")),
        ),
    )


def render_signup(next_url: str) -> HtmlElement:
    return page(
        "Sign up",
        h.Main(
            {"id": "signup"},
            data.signals(
                {"username": "", "email": "", "password": "", "next": next_url, "_error": ""}
            ),
            h.H1("Sign up"),
            h.Form(
                data.on("submit", at.post(SIGN_UP.href()), prevent=True),
                field("Username", "username"),
                field("Email", "email", "email"),
                field("Password", "password", "password"),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
                h.Button({"type": "submit"}, "Sign up"),
            ),
            h.P(h.A({"href": LOGIN.href(query={"next": next_url})}, "Have an account?")),
        ),
    )
