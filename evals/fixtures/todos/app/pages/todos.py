from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import PAGE_SIZE, TODOS_PAGE, Todo, add_todo, list_todos
from app.layout import page
from app.urls import ADD_TODO, TODOS, TODOS_LIVE


def page_number(c: Context) -> int:
    raw = c.req.query.get("page", "1")
    return int(raw) if raw.isdecimal() and int(raw) > 0 else 1


@dataclass(frozen=True, slots=True)
class TodosPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(TODOS, self.show)
        app.add(TODOS_LIVE, self.live)
        app.add(ADD_TODO, self.add)

    async def show(self, c: Context, w: Writer) -> None:
        n = page_number(c)
        w.html(render(list_todos(self.db, n), n))

    async def live(self, c: Context, w: Writer) -> None:
        n, sse = page_number(c), SSE(w)
        offset = (n - 1) * PAGE_SIZE
        async with self.db.watch(TODOS_PAGE, Todo, limit=PAGE_SIZE, offset=offset) as rows:
            async for todos in c.alive(rows):
                sse.patch_elements(render(todos, n))

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not 1 <= len(title) <= 200:
            SSE(w).patch_signals({"_error": "title must be 1 to 200 characters"})
            return
        await self.db.write(add_todo, title)
        SSE(w).patch_signals({"title": "", "_error": ""})


def render(todos: list[Todo], n: int) -> HtmlElement:
    return page(
        "Todos",
        h.Main(
            {"id": "todos"},
            data.signals({"title": "", "_error": ""}, if_missing=True),
            data.init(at.get(TODOS_LIVE.href(query={"page": n}), retry="always")),
            h.Form(
                data.on("submit", at.post(ADD_TODO.href()), prevent=True),
                h.Input({"name": "title", "maxlength": 200}, data.bind("title")),
                h.Button({"type": "submit"}, "Add"),
            ),
            h.P({"class": "error"}, data.show("$_error"), data.text("$_error")),
            h.Ul(*[h.Li(t.title) for t in todos]),
            h.A({"href": TODOS.href(query={"page": n + 1})}, "Older"),
        ),
    )
