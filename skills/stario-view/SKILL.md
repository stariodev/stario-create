---
name: stario-view
description: Sort, filter, or page a Stario list through the URL query, and search as you type that patches one part. Use when a list gets sort links, filters, paging, or a search box.
---

# A view in the URL, and search as you type

This skill extends the todos page of AGENTS.md. Two kinds of "what this tab sees":

- **A view**: a sort, a filter, a page number. It is in the URL query, so a reload, a shared link, and the back button show the same thing, and each tab has its own. A `View` dataclass in `app/urls.py` reads and writes it.
- **A private read**: a result only this tab needs while the user types. A `GET` reads the signals and patches one part. It keeps nothing.

## A view

```python
# app/urls.py (the imports go at the top of the file)
from dataclasses import dataclass

from stario.http.query import ParsedQuery

SORTS = ("new", "old", "title")


@dataclass(frozen=True, slots=True)
class TodosView:
    sort: str = "new"
    page: int = 1

    @classmethod
    def from_query(cls, query: ParsedQuery) -> TodosView:
        sort, page = query.get("sort", "new"), query.get("page", "1")
        number = int(page) if page.isdecimal() and int(page) > 0 else 1
        return cls(sort if sort in SORTS else "new", number)

    def query(self) -> dict[str, str]:
        return {"sort": self.sort, "page": str(self.page)}
```

An unknown value falls back to the default, so an old link still opens.

```python
# app/data.py: one fixed SQL text per sort; a filter is a :parameter
SORTED = {
    "new": "SELECT id, title FROM todos ORDER BY id DESC LIMIT :limit OFFSET :offset",
    "old": "SELECT id, title FROM todos ORDER BY id LIMIT :limit OFFSET :offset",
    "title": "SELECT id, title FROM todos ORDER BY lower(title) LIMIT :limit OFFSET :offset",
}


def list_sorted(db: LiteWriter, sort: str, page: int) -> list[Todo]:
    return db.query(SORTED[sort], Todo, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
```

`ORDER BY` cannot be a parameter, so each sort key picks one constant SQL text. Every outside value is a `:name` parameter.

```python
# app/pages/<page>.py: the page GET and the stream read the same view
async def show(self, c: Context, w: Writer) -> None:
    view = TodosView.from_query(c.req.query)
    w.html(render(list_sorted(self.db, view.sort, view.page), view))


async def live(self, c: Context, w: Writer) -> None:
    view, sse = TodosView.from_query(c.req.query), SSE(w)
    offset = (view.page - 1) * PAGE_SIZE
    async with self.db.watch(SORTED[view.sort], Todo, limit=PAGE_SIZE, offset=offset) as rows:
        async for todos in c.alive(rows):
            sse.patch_elements(render(todos, view))


def render(todos: list[Todo], view: TodosView) -> HtmlElement:
    return page(
        "Todos",
        h.Main(
            {"id": "todos"},
            data.signals({"title": "", "_error": ""}, if_missing=True),
            data.init(at.get(TODOS_LIVE.href(query=view.query()), retry="always")),
            # the form and the error <p> from AGENTS.md stay here
            h.Nav(
                *[
                    h.A(
                        {
                            "href": TODOS.href(query=replace(view, sort=s, page=1).query()),
                            "aria-current": "true" if s == view.sort else None,
                        },
                        s,
                    )
                    for s in SORTS
                ]
            ),
            h.Ul(*[h.Li(t.title) for t in todos]),
            h.A({"href": TODOS.href(query=replace(view, page=view.page + 1).query())}, "Older"),
        ),
    )
```

`replace` is `dataclasses.replace`. The stream URL carries the view, so the `data.init` text is the same in every render of this tab. A new sort is a link: the browser loads the new URL, opens a new stream, and closes the old one. The commands do not change. A test: `client.get(TODOS.href(query={"sort": "old"}))` and assert the order in `r.text`.

## Search as you type

The result only this tab needs. It changes no state, so it needs no stream.

```python
# app/urls.py
SEARCH = Route("GET /search")
SEARCH_RESULTS = Route("GET /search/results")
```

```python
# app/pages/search.py
from dataclasses import dataclass

from stario import App, Context, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.layout import page
from app.urls import SEARCH, SEARCH_RESULTS


@dataclass(frozen=True, slots=True)
class SearchPage:
    cities: tuple[str, ...]

    def register(self, app: App) -> None:
        app.add(SEARCH, self.show)
        app.add(SEARCH_RESULTS, self.results)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(list(self.cities[:20]), len(self.cities)))

    async def results(self, c: Context, w: Writer) -> None:
        q = str((await read_signals(c.req)).get("q", "")).strip().lower()
        found = [city for city in self.cities if q in city.lower()]
        SSE(w).patch_elements(results(found[:20], len(found)))


def results(matches: list[str], total: int) -> HtmlElement:
    return h.Div({"id": "results"}, h.P(f"{total} matches"), h.Ul(*[h.Li(m) for m in matches]))


def render(matches: list[str], total: int) -> HtmlElement:
    return page(
        "Search",
        h.Main(
            {"id": "search"},
            data.signals({"q": ""}, if_missing=True),
            h.Input(
                {"type": "search"},
                data.bind("q"),
                data.on("input", at.get(SEARCH_RESULTS.href()), debounce="200ms"),
            ),
            results(matches, total),
        ),
    )
```

- Patch the results, never the input: a repaint of a control loses what the user typed.
- A test: `client.get(SEARCH_RESULTS.href(), params={"datastar": '{"q": "par"}'})`, then assert the matches in `r.text`.
- A text too long for a URL: `POST` with the same handler shape. It still changes no state.
- A search that must survive a reload or a shared link is a view: a `<form method="get">` reloads the page with `?q=`.
