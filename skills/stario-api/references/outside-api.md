# An outside HTTP API with a cache

One `httpx.AsyncClient` per app, opened in `bootstrap`; one class that knows the API's
shape, in `app/<api>.py`; a page that takes it as a field. Verified with httpx 0.28.

```bash
uv add httpx
```

```python
# app/pokeapi.py
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class Missing(Exception):
    """The API has no such resource (a 404)."""


@dataclass(slots=True)
class PokeApi:
    http: httpx.AsyncClient
    ttl: float = 3600
    cache: dict[str, tuple[float, Any]] = field(default_factory=dict)

    async def get(self, path: str) -> Any:
        """The JSON at `path`. A 404 raises Missing; other errors raise httpx errors."""
        hit = self.cache.get(path)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        r = await self.http.get(path)
        if r.status_code == 404:
            raise Missing(path)
        r.raise_for_status()
        self.cache[path] = (time.monotonic(), r.json())
        return self.cache[path][1]
```

- Return `Any`, and raise for a missing resource. `-> Any | None` makes pyrefly refuse every `result["name"]` that follows.
- A page catches `Missing` and answers its 404 page: `w.html(not_found_page(), status=404)`.
- The cache is a field of the object built in `bootstrap`, never a module-level dict.

In `bootstrap`, next to the pages (`api_url` is a `Config` field, read from `API_URL`):

```python
async with httpx.AsyncClient(base_url=config.api_url, timeout=10) as http:
    api = PokeApi(http)
    PokemonPage(api).register(app)
    yield
```

A test fakes the API with `httpx.MockTransport`, so it needs no network and no server:

```python
# tests/test_pokeapi.py
import httpx
import pytest

from app.pokeapi import Missing, PokeApi


async def test_the_cache_asks_once():
    calls: list[str] = []

    def answer(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/pokemon/none":
            return httpx.Response(404)
        return httpx.Response(200, json={"name": "pikachu"})

    transport = httpx.MockTransport(answer)
    async with httpx.AsyncClient(base_url="https://x", transport=transport) as http:
        api = PokeApi(http)
        assert (await api.get("/pokemon/25"))["name"] == "pikachu"
        assert (await api.get("/pokemon/25"))["name"] == "pikachu"
        with pytest.raises(Missing):
            await api.get("/pokemon/none")
    assert calls == ["/pokemon/25", "/pokemon/none"]
```

A page test with the fake: give `bootstrap` the transport through a `Config` field, or
build the page with `PokeApi(http)` on a `TestClient` of a small `App`. When the task
ships an acceptance suite that starts the real API, that suite is the check; the page
check in `tests/test_pages.py` skips a page whose API is not running.
