import asyncio

from litewriter import LiteWriter, Tx
from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.common.oidc import Http, Issuer
from app.common.session import Session
from app.config import Config
from app.features.home.handlers import HomePage
from app.features.login import data as login_data
from app.features.login.handlers import LoginPage
from app.features.login.urls import LOGIN


def schema(tx: Tx) -> None:
    login_data.schema(tx)


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db:
        secure = not config.app_dev
        keys = [config.session_secret]
        # __Host- keeps a subdomain from setting the cookie; it needs Secure.
        session = Session(
            SignedCookie("__Host-session" if secure else "session", keys=keys, secure=secure),
            LOGIN.href(),
        )
        # The state, nonce, and PKCE verifier of one sign-in, for 10 minutes.
        flow = SignedCookie(
            "__Host-login" if secure else "login", keys=keys, secure=secure, max_age=600
        )
        issuer = Issuer(
            config.login_issuer, config.login_client_id, config.login_client_secret, Http()
        )
        app.use("/", same_origin(), security_headers(), session.attach)
        app.use("/app", session.require)
        span.attrs(await ASSETS.attach(app))
        HomePage(config.app_name).register(app)
        LoginPage(
            db,
            session,
            issuer,
            flow,
            allowed=config.allowed_emails,
            scheme="https" if secure else "http",
        ).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
