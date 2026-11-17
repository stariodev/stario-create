---
name: stario-outside-api
description: Call an outside HTTP API from a Stario app - an httpx client opened in bootstrap, a cache, a 404 page, tests that fake the API. Use when pages read data from another service over HTTP.
---

# An outside HTTP API

Stario has no HTTP client. One `httpx.AsyncClient` per app, opened in `bootstrap`; one class that knows the API's shape, in `app/<api>.py`; a page that takes it as a field, like `db`. Verified with httpx 0.28.

```bash
uv add httpx
```

```python
# app/books.py
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class Missing(Exception):
    """The API has no such resource (a 404)."""


@dataclass(slots=True)
class BooksApi:
    http: httpx.AsyncClient
    ttl: float = 3600
    cache: dict[str, tuple[float, Any]] = field(default_factory=dict)

    async def get(self, path: str, **params: str) -> Any:
        """The JSON at `path`. A 404 raises Missing; other errors raise httpx errors."""
        key = str(httpx.URL(path, params=params))
        hit = self.cache.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        r = await self.http.get(path, params=params)
        if r.status_code == 404:
            raise Missing(key)
        r.raise_for_status()
        self.cache[key] = (time.monotonic(), r.json())
        return self.cache[key][1]
```

- Return `Any`, and raise for a missing resource. `-> Any | None` makes pyrefly refuse every `result["title"]` that follows.
- The cache is a field of the object built in `bootstrap`, never a module-level dict.
- Many calls for one page: `await asyncio.gather(*[api.get(p) for p in paths])`.

In `bootstrap`, next to the pages (`api_url` is a `Config` field, read from `API_URL`):

```python
async with httpx.AsyncClient(base_url=config.api_url, timeout=10) as http:
    api = BooksApi(http)
    BookPage(api).register(app)
    yield
```

A page catches `Missing` and answers 404:

```python
async def show(self, c: Context, w: Writer) -> None:
    try:
        book = await self.api.get(f"/works/{c.match.params['work_id']}.json")
    except Missing:
        w.text("not found", status=404)
        return
    w.html(render(book))
```

## Tests

A test fakes the API with `httpx.MockTransport`, so it needs no network and no server:

```python
# tests/test_books.py
import httpx
import pytest

from app.books import BooksApi, Missing


async def test_the_cache_asks_once():
    calls: list[str] = []

    def answer(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/works/none.json":
            return httpx.Response(404)
        return httpx.Response(200, json={"title": "Dune"})

    transport = httpx.MockTransport(answer)
    async with httpx.AsyncClient(base_url="https://x", transport=transport) as http:
        api = BooksApi(http)
        assert (await api.get("/works/1.json"))["title"] == "Dune"
        assert (await api.get("/works/1.json"))["title"] == "Dune"
        with pytest.raises(Missing):
            await api.get("/works/none.json")
    assert calls == ["/works/1.json", "/works/none.json"]
```

A page test with the fake: give `bootstrap` the transport through a `Config` field, or build the page with `BooksApi(http)` on a `TestClient` of a small `App`. The page check in `tests/test_pages.py` skips a page whose API is not running. When the task ships an acceptance suite, that suite is the check: write none of these tests.
