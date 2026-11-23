import asyncio

from litewriter import LiteWriter
from stario import App, Span, serve
from stario.http import same_origin, security_headers

from app.config import Config
from app.data import schema
from app.layout import ASSETS
from app.pages.home import HomePage
from app.pages.todos import TodosPage


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db:
        app.use("/", same_origin(), security_headers())
        span.attrs(await ASSETS.attach(app))
        # pages: one register line each
        HomePage(config.app_name).register(app)
        TodosPage(db).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))  # listens on STARIO_HOST:STARIO_PORT, default 127.0.0.1:8000
