import asyncio
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer
from stario.datastar import SSE, read_signals

from app.common.session import Session, check_password, current_user
from app.features.home.urls import HOME
from app.features.login.data import get_login
from app.features.login.urls import LOGIN, LOGIN_POST, LOGOUT
from app.features.login.views import render


@dataclass(frozen=True, slots=True)
class LoginPage:
    db: LiteWriter
    session: Session

    def register(self, app: App) -> None:
        app.add(LOGIN, self.show)
        app.add(LOGIN_POST, self.submit)
        app.add(LOGOUT, self.logout)

    async def show(self, c: Context, w: Writer) -> None:
        if current_user(c):
            w.redirect(HOME.href(), status=303)
            return
        w.html(render())

    async def submit(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        email = str(signals.get("email", "")).strip().lower()
        password = str(signals.get("password", ""))
        login = get_login(self.db, email)
        if login is None or not await asyncio.to_thread(check_password, password, login[1]):
            SSE(w).patch_signals({"password": "", "_error": "Wrong email or password."})
            return
        self.session.issue(w, login[0])
        SSE(w).navigate(HOME.href())

    async def logout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        SSE(w).navigate(LOGIN.href())
