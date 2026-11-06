import asyncio

from litewriter import LiteWriter, Tx
from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.common.providers import GOOGLE, GitHub, Http, Issuer, Provider
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
        http = Http()
        # Each provider is on when its client pair is set. The key is its name in /login/<name>.
        providers: dict[str, Provider] = {}
        if config.google_client_id:
            providers["google"] = Issuer(
                GOOGLE, config.google_client_id, config.google_client_secret, http
            )
        if config.github_client_id:
            providers["github"] = GitHub(config.github_client_id, config.github_client_secret, http)
        if config.oidc_client_id:
            providers["oidc"] = Issuer(
                config.oidc_issuer, config.oidc_client_id, config.oidc_client_secret, http
            )
        app.use("/", same_origin(), security_headers(), session.attach)
        app.use("/app", session.require)
        span.attrs(await ASSETS.attach(app))
        HomePage(config.app_name).register(app)
        LoginPage(
            db,
            session,
            providers,
            flow,
            allowed=config.allowed_emails,
            scheme="https" if secure else "http",
        ).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
