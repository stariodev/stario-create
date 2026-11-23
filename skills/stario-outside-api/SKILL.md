---
name: stario-outside-api
description: Call an outside HTTP API from a Stario app - an httpx client opened in bootstrap, typed results, a cache, a 404 or 502 page when the service fails, offline tests with httpx.MockTransport. Use when pages read data from another service over HTTP.
---

# An outside HTTP API

First, in the app folder: `uv add httpx` (the scaffold lacks it; without it `check` fails at
`import httpx`). Open one `httpx.AsyncClient` in bootstrap, wrap it in a small class with the
calls the pages need, and pass that object to the page classes. Never a client or a cache at
module level (the lint refuses module state): each test gets its own.

```python
# app/books.py
"""The book service: every call the pages make, typed, with a cache."""

import time
from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True, slots=True)
class Book:
    key: str
    title: str
    year: int | None


def http_client(base_url: str) -> httpx.AsyncClient:
    """Bootstrap opens it; a test replaces this function to answer offline."""
    return httpx.AsyncClient(base_url=base_url, timeout=10)


@dataclass(slots=True)
class Books:
    http: httpx.AsyncClient
    ttl: float = 600  # seconds an answer stays fresh
    cache: dict[str, tuple[float, list[Book]]] = field(default_factory=dict)

    async def search(self, q: str) -> list[Book]:
        hit = self.cache.get(q)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]
        r = await self.http.get("/search.json", params={"q": q, "limit": 20})
        r.raise_for_status()
        books = [
            Book(str(d["key"]), str(d.get("title", "")), d.get("first_publish_year"))
            for d in r.json().get("docs", [])
        ]
        self.cache[q] = (time.monotonic() + self.ttl, books)
        return books

    async def get(self, key: str) -> Book | None:
        """One item, or None when the service has none (its 404)."""
        r = await self.http.get(f"/works/{key}.json")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        doc = r.json()
        return Book(key, str(doc.get("title", "")), None)
```

Each call returns dataclasses with plain types, never `Any` or `dict | None`: pyrefly then checks
the pages. Convert at the edge (`str(...)`, `int(...)`, `.get(key, default)`).

```python
# app/pages/books.py
from dataclasses import dataclass

from stario import App, Context, Route, Writer, h

from app.books import Books
from app.layout import page

BOOKS = Route("GET /books")  # in app/urls.py in a real app


@dataclass(frozen=True, slots=True)
class BooksPage:
    books: Books

    def register(self, app: App) -> None:
        app.add(BOOKS, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        q = c.req.query.get("q", "").strip()
        found = await self.books.search(q) if q else []
        w.html(page("Books", h.Ul(*[h.Li(b.title) for b in found])))
```

A page never catches the service's errors itself: one middleware answers for every page.

```python
# app/pages/errors.py
from stario import Context, Writer, h

from app.layout import page


async def service_down(c: Context, w: Writer, exc: BaseException) -> None:
    """Every page whose service fails: 502 and a notice. The trace keeps the cause."""
    c.span.exception(exc)  # the page check skips a page whose trace shows a connect error
    w.html(
        page("Unavailable", h.P("The book service does not answer. Try again soon.")), status=502
    )
```

In bootstrap (a Config field `books_url: str = "https://openlibrary.org"` reads `BOOKS_URL`;
`catch_errors` is in `stario.http`, `service_down` in `app.pages.errors`):

```python
app.use("/", same_origin(), security_headers(), catch_errors(httpx.HTTPError, respond=service_down))
...
async with http_client(config.books_url) as http:
    BooksPage(Books(http)).register(app)
    yield
```

Data from the service changes: read it at request time and cache in memory for a while; never
copy it into files at build time. A missing item answers the app's own 404 page.

## Tests, offline

Replace `http_client` before the app starts, with a `MockTransport` that answers like the
service:

```python
# tests/test_books.py
import httpx
import pytest
from stario.testing import TestClient

from app.main import bootstrap


def fake(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/search.json":
        return httpx.Response(200, json={"docs": [{"key": "/works/1", "title": "Dune"}]})
    return httpx.Response(404)


@pytest.fixture
async def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.main.http_client",
        lambda base_url: httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(fake)),
    )
    async with TestClient(bootstrap) as client:
        yield client


async def test_search_lists_the_titles(offline):
    assert "Dune" in (await offline.get("/books", params={"q": "dune"})).text
```

The generated page check skips a page whose service is down (a connect error or a timeout in
its trace), so `check` passes offline. When the task runs a local copy of the service, point the Config field
at it through its env var.
