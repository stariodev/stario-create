import hmac
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer
from stario.cookies import SignedCookie
from stario.datastar import SSE
from stario.forms import read_form

from app.common.providers import Flow, LoginFailed, Provider
from app.common.session import Session, current_user, local_path
from app.features.home.urls import HOME
from app.features.login.data import add_login
from app.features.login.urls import LOGIN, LOGIN_CALLBACK, LOGIN_START, LOGOUT
from app.features.login.views import render


@dataclass(frozen=True, slots=True)
class LoginPage:
    db: LiteWriter
    session: Session
    providers: Mapping[str, Provider]
    flow: SignedCookie
    allowed: frozenset[str]
    scheme: str

    def register(self, app: App) -> None:
        app.add(LOGIN, self.show)
        app.add(LOGIN_START, self.start)
        app.add(LOGIN_CALLBACK, self.callback)
        app.add(LOGOUT, self.logout)

    async def show(self, c: Context, w: Writer) -> None:
        next_url = local_path(c.req.query.get("next", ""), HOME.href())
        if current_user(c):
            w.redirect(next_url, status=303)
            return
        error = str(c.req.query.get("error", ""))
        w.html(render(list(self.providers), next_url, error))

    async def start(self, c: Context, w: Writer) -> None:
        name = c.match.params["provider"]
        provider = self.providers.get(name)
        if provider is None:
            w.text("unknown provider", status=404)
            return
        with await read_form(c.req) as form:
            next_url = local_path(form.get("next", ""), HOME.href())
        flow = Flow.new()
        try:
            url = await provider.authorize_url(self._callback_url(c, name), flow)
        except LoginFailed as e:
            self._fail(c, w, "failed", str(e))
            return
        data = {"state": flow.state, "nonce": flow.nonce, "verifier": flow.verifier}
        self.flow.set(w, data | {"provider": name, "next": next_url})
        w.redirect(url, status=303)

    async def callback(self, c: Context, w: Writer) -> None:
        # A GET that signs in: the state check ties it to the start in this browser.
        name = c.match.params["provider"]
        provider = self.providers.get(name)
        if provider is None:
            w.text("unknown provider", status=404)
            return
        saved = self.flow.get(c.req)
        data = saved.data if saved is not None else {}
        state = str(c.req.query.get("state", ""))
        # The flow cookie stays until a callback matches it, so a forged GET from
        # another site cannot end a sign-in that is still open.
        if data.get("provider") != name or not hmac.compare_digest(
            str(data.get("state", "")), state
        ):
            self._fail(c, w, "expired", "no flow cookie, another state, or another provider")
            return
        self.flow.delete(w)
        if c.req.query.get("error"):
            self._fail(c, w, "denied", str(c.req.query.get("error")))
            return
        code = str(c.req.query.get("code", ""))
        if not code:
            self._fail(c, w, "expired", "no code")
            return
        flow = Flow(data["state"], data["nonce"], data["verifier"])
        try:
            who = await provider.identity(code, self._callback_url(c, name), flow)
        except LoginFailed as e:
            self._fail(c, w, "failed", str(e))
            return
        if self.allowed and not (who.email_verified and who.email in self.allowed):
            self._fail(c, w, "not_allowed", who.email)
            return
        user_id = await self.db.write(add_login, who, str(uuid.uuid7()))
        self.session.issue(w, user_id)
        w.redirect(local_path(data.get("next"), HOME.href()), status=303)

    async def logout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        if c.req.headers.get("datastar-request"):
            SSE(w).navigate(LOGIN.href())
        else:
            w.redirect(LOGIN.href(), status=303)

    def _callback_url(self, c: Context, name: str) -> str:
        # The provider compares it with the callback URLs registered there, and the
        # exchange needs the client secret, so a forged Host cannot finish a sign-in.
        return f"{self.scheme}://{c.req.host}{LOGIN_CALLBACK.href(name)}"

    def _fail(self, c: Context, w: Writer, error: str, reason: str) -> None:
        c.span.attrs({"login.error": error, "login.reason": reason})
        w.redirect(LOGIN.href(query={"error": error}), status=303)
