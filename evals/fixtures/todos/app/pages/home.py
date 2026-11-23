from dataclasses import dataclass

from stario import App, Context, Route, Writer, h
from stario.markup import HtmlElement

from app.layout import page
from app.urls import HOME, TODOS

# The home page links to each page: one (route, label) line per page.
LINKS: tuple[tuple[Route, str], ...] = ((TODOS, "Todos"),)


@dataclass(frozen=True, slots=True)
class HomePage:
    app_name: str

    def register(self, app: App) -> None:
        app.add(HOME, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(self.app_name))


def render(app_name: str) -> HtmlElement:
    return page(
        app_name,
        h.Main(
            {"id": "home"},
            h.H1(app_name),
            h.P("Stario is running. Read AGENTS.md, then add a page."),
            h.Nav(h.Ul(*[h.Li(h.A({"href": route.href()}, label)) for route, label in LINKS])),
        ),
    )
