"""Sign up, sign in, sign out: plain HTML forms that work with any spec and without JS.

Change the paths in app/urls.py and the markup below to fit the app; keep the route
names and the field names (email, password, username) and tests/test_login.py still holds.
"""

import asyncio
from dataclasses import dataclass

import apsw
from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.forms import read_form
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
            w.redirect(next_url, 303)
            return
        w.html(render_login(next_url))

    async def show_signup(self, c: Context, w: Writer) -> None:
        w.html(render_signup(local_path(c.req.query.get("next", ""), HOME.href())))

    async def sign_in(self, c: Context, w: Writer) -> None:
        form = await read_form(c.req)
        email = form.get("email", "").strip()
        password = form.get("password", "")
        next_url = local_path(form.get("next", ""), HOME.href())
        login = get_login(self.db, email)
        # A missing user still costs one hash, so the answer time does not tell.
        stored = login.hash if login is not None else _DUMMY
        if not await asyncio.to_thread(check_password, password, stored) or login is None:
            w.html(render_login(next_url, email, "email or password is invalid"), 422)
            return
        self.session.issue(w, login.id)
        w.redirect(next_url, 303)

    async def sign_up(self, c: Context, w: Writer) -> None:
        form = await read_form(c.req)
        username = form.get("username", "").strip()
        email = form.get("email", "").strip()
        password = form.get("password", "")
        next_url = local_path(form.get("next", ""), HOME.href())
        error = ""
        if not 1 <= len(username) <= 40:
            error = "a username is required"
        elif "@" not in email or len(email) > 200:
            error = "an email is required"
        elif len(password) < 8:
            error = "the password needs 8 or more characters"
        if not error:
            # The hash runs before the write: a write function holds no slow work.
            hashed = await asyncio.to_thread(hash_password, password)
            try:
                user_id = await self.db.write(add_user, email, username, hashed)
            except apsw.ConstraintError:
                error = "that email or username is taken"
            else:
                self.session.issue(w, user_id)
                w.redirect(next_url, 303)
                return
        w.html(render_signup(next_url, username, email, error), 422)

    async def logout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        w.redirect(HOME.href(), 303)


_DUMMY = hash_password("not a password")


def errors(error: str) -> HtmlElement:
    return h.Ul({"class": "errors", "role": "alert"}, h.Li(error)) if error else None


def field(label: str, name: str, kind: str = "text", value: str = "") -> HtmlElement:
    return h.Label(label, h.Input({"type": kind, "name": name, "value": value, "required": True}))


def render_login(next_url: str, email: str = "", error: str = "") -> HtmlElement:
    return page(
        "Sign in",
        h.Main(
            {"id": "login"},
            h.H1("Sign in"),
            errors(error),
            h.Form(
                {"method": "post", "action": SIGN_IN.href()},
                h.Input({"type": "hidden", "name": "next", "value": next_url}),
                field("Email", "email", "email", email),
                field("Password", "password", "password"),
                h.Button({"type": "submit"}, "Sign in"),
            ),
            h.P(h.A({"href": SIGNUP.href(query={"next": next_url})}, "Need an account?")),
        ),
    )


def render_signup(
    next_url: str, username: str = "", email: str = "", error: str = ""
) -> HtmlElement:
    return page(
        "Sign up",
        h.Main(
            {"id": "signup"},
            h.H1("Sign up"),
            errors(error),
            h.Form(
                {"method": "post", "action": SIGN_UP.href()},
                h.Input({"type": "hidden", "name": "next", "value": next_url}),
                field("Username", "username", "text", username),
                field("Email", "email", "email", email),
                field("Password", "password", "password"),
                h.Button({"type": "submit"}, "Sign up"),
            ),
            h.P(h.A({"href": LOGIN.href(query={"next": next_url})}, "Have an account?")),
        ),
    )
