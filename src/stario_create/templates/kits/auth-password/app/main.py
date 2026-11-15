import asyncio

from litewriter import LiteWriter, Tx
from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app import data
from app.auth import data as auth_data
from app.auth.session import Session
from app.config import Config
from app.layout import ASSETS
from app.pages.home import HomePage
from app.pages.login import LoginPage
from app.urls import LOGIN


def schema(tx: Tx) -> None:
    auth_data.schema(tx)
    data.schema(tx)


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db:
        secure = not config.app_dev
        # __Host- keeps a subdomain from setting the cookie; it needs Secure.
        cookie = SignedCookie(
            "__Host-session" if secure else "session", keys=[config.session_secret], secure=secure
        )
        session = Session(cookie, LOGIN.href())
        app.use("/", same_origin(), security_headers(), session.attach)
        # Pages for signed-in users: app.use("/editor", session.require), or
        # app.add(ROUTE, handler, middleware=[session.require]) for one route.
        app.use("/app", session.require)
        span.attrs(await ASSETS.attach(app))
        # pages: one register line each
        HomePage(config.app_name).register(app)
        LoginPage(db, session).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))  # listens on STARIO_HOST:STARIO_PORT, default 127.0.0.1:8000
