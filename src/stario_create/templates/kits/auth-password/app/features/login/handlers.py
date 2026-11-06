import asyncio
import secrets
from dataclasses import dataclass

from stario import App, Context, Writer
from stario.datastar import SSE, read_signals

from app.common.session import Session, Tries, check_password, current_user, hash_password
from app.features.home.urls import HOME
from app.features.login.urls import LOGIN, LOGIN_POST, LOGOUT
from app.features.login.views import render

# An unknown email still pays for one hash, so the answer time does not tell who has an account.
_NOBODY = hash_password(secrets.token_urlsafe(16))


@dataclass(frozen=True, slots=True)
class LoginPage:
    session: Session
    accounts: dict[str, str]
    tries: Tries

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
        known = email in self.accounts
        if known and self.tries.locked(email):
            SSE(w).patch_signals({"password": "", "_error": "Too many tries. Wait 15 minutes."})
            return
        stored = self.accounts.get(email, _NOBODY)
        if not await asyncio.to_thread(check_password, password, stored) or not known:
            if known:
                self.tries.fail(email)
            SSE(w).patch_signals({"password": "", "_error": "Wrong email or password."})
            return
        self.tries.clear(email)
        self.session.issue(w, email)
        SSE(w).navigate(HOME.href())

    async def logout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        SSE(w).navigate(LOGIN.href())
