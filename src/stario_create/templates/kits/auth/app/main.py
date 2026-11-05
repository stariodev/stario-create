import asyncio
import uuid

from litewriter import LiteWriter, Tx
from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.common.session import Session, hash_password
from app.config import Config
from app.features.home.handlers import HomePage
from app.features.login import data as login_data
from app.features.login.handlers import LoginPage
from app.features.login.urls import LOGIN
from app.features.signup.handlers import SignupPage


def schema(tx: Tx) -> None:
    login_data.schema(tx)


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db:
        if config.admin_email and login_data.count_users(db) == 0:
            password_hash = await asyncio.to_thread(hash_password, config.admin_password)
            await db.write(
                login_data.add_user, str(uuid.uuid7()), config.admin_email, password_hash
            )
        # __Host- keeps a subdomain from setting the cookie; it needs Secure.
        cookie = SignedCookie(
            "session" if config.dev else "__Host-session",
            keys=[config.session_secret],
            secure=not config.dev,
        )
        session = Session(cookie, LOGIN.href())
        app.use("/", same_origin(), security_headers(), session.attach)
        app.use("/app", session.require)
        span.attrs(await ASSETS.attach(app))
        HomePage(config.app_name).register(app)
        LoginPage(db, session).register(app)
        SignupPage(db, session).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
