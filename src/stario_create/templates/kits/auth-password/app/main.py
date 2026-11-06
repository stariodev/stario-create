import asyncio

from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.common.session import Session, Tries
from app.config import Config
from app.features.home.handlers import HomePage
from app.features.login.handlers import LoginPage
from app.features.login.urls import LOGIN


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    secure = not config.app_dev
    # __Host- keeps a subdomain from setting the cookie; it needs Secure.
    cookie = SignedCookie(
        "__Host-session" if secure else "session", keys=[config.session_secret], secure=secure
    )
    session = Session(cookie, LOGIN.href())
    app.use("/", same_origin(), security_headers(), session.attach)
    app.use("/app", session.require)
    span.attrs(await ASSETS.attach(app))
    HomePage(config.app_name).register(app)
    LoginPage(session, config.accounts, Tries()).register(app)
    yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
