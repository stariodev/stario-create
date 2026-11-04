"""The page check: each HTML page that a link or a GET route in urls.py reaches.

It needs no edit. A page test with rows calls `assert not await check(client, url)`.
"""

import importlib
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from stario import Route

FEATURES = Path(__file__).parent.parent / "app" / "features"
LIMIT = 50

ACTION = re.compile(r"@(get|post|put|patch|delete)\(\s*'([^']*)'")
SIGNAL = re.compile(r"\$([A-Za-z_]\w*)")
ASSIGN = re.compile(r"\$([A-Za-z_]\w*)\s*=(?!=)")
KEY = re.compile(r"['\"]([A-Za-z_]\w*)['\"]\s*:")
QUOTED = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, list[tuple[str, str]], str]] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pairs = [(k, v or "") for k, v in attrs]
        self.tags.append((tag, pairs, self.get_starttag_text() or ""))
        if tag == "a":
            self.links += [v for k, v in pairs if k == "href"]


def parse(html: str) -> Page:
    page = Page()
    page.feed(html)
    return page


def defined(page: Page) -> set[str]:
    names = {"_toast"}
    for _, attrs, _ in page.tags:
        for key, value in attrs:
            base, _, suffix = key.partition(":")
            base = base.split("__")[0]
            if base in ("data-bind", "data-ref", "data-indicator") and not suffix:
                names.add(value)
            elif base in ("data-signals", "data-computed", "data-signal", "data-bind") and suffix:
                names.add(suffix.split("__")[0].replace("-", "_"))
            elif base in ("data-signals", "data-computed"):
                try:
                    names |= set(json.loads(value))
                except ValueError:
                    names |= set(KEY.findall(value))
            if key.startswith("data-"):
                names |= set(ASSIGN.findall(QUOTED.sub("", value)))
    return names


def problems(client, url: str, page: Page) -> list[str]:
    found = []
    names = defined(page)
    ids: set[str] = set()
    for tag, attrs, _ in page.tags:
        for key, value in attrs:
            if key == "id":
                if value in ids:
                    found.append(f"{url}: two elements have id={value!r}")
                ids.add(value)
            if not key.startswith("data-") or key.startswith("data-signals"):
                continue
            for method, target in ACTION.findall(value):
                path = urlsplit(unescape(target)).path
                _, route, _ = client.app.find_handler("localhost", path, method.upper())
                if route is Route.empty():
                    found.append(f"{url}: {method.upper()} {path} has no route")
            for name in SIGNAL.findall(QUOTED.sub("", value)):
                if name not in names:
                    found.append(f"{url}: {key} reads ${name}, which no element defines")
        if tag == "dialog" and "open" not in dict(attrs).get("data-preserve-attr", ""):
            found.append(f'{url}: a <dialog> has no data.preserve_attr("open")')
    return found


def signals(page: Page) -> str:
    """The signals a Datastar request sends: every one without a leading _."""
    values: dict = {}
    for _, attrs, _ in page.tags:
        for key, value in attrs:
            if key.split("__")[0] == "data-signals":
                try:
                    values |= {k: v for k, v in json.loads(value).items() if k[0] != "_"}
                except ValueError:
                    pass
    return json.dumps(values)


async def stream_problems(client, url: str, page: Page) -> list[str]:
    found = []
    for tag, attrs, text in page.tags:
        init = dict(attrs).get("data-init", "")
        match = ACTION.search(init)
        if not match or match[1] != "get":
            continue
        if "id" not in dict(attrs):
            found.append(f"{url}: <{tag} data-init> opens a stream but has no id")
            continue
        live = unescape(match[2])
        async with client.stream(
            "GET", live, params={"datastar": signals(page)}, timeout=2
        ) as response:
            if response.status_code != 200:
                found.append(f"{url}: the stream {live} answers {response.status_code}")
                continue
            first = (await anext(response.iter_events()))["data"]
        if text not in first:
            found.append(f"{url}: the stream {live} changes the tag {text}")
    return found


async def check(client, url: str) -> list[str]:
    """The problems of one page. Empty when the page is not HTML."""
    r = await client.get(url)
    if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
        return []
    page = parse(r.text)
    return problems(client, url, page) + await stream_problems(client, url, page)


async def html_routes(client) -> list[str]:
    """Each GET route with no path parameter in app/features/*/urls.py that answers HTML."""
    found = []
    for path in sorted(FEATURES.glob("*/urls.py")):
        urls = importlib.import_module(f"app.features.{path.parent.name}.urls")
        for route in vars(urls).values():
            if not isinstance(route, Route) or route.method != "GET" or "{" in route.target:
                continue
            async with client.stream("GET", route.href(), timeout=2) as r:
                if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                    found.append(route.href())
    return found


async def test_every_page_checks_out(client):
    queue, seen, found = ["/", *await html_routes(client)], set(), []
    while queue and len(seen) < LIMIT:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        found += await check(client, url)
        r = await client.get(url)
        for href in parse(r.text).links if r.status_code == 200 else []:
            parts = urlsplit(href)
            if not parts.scheme and not parts.netloc and parts.path.startswith("/"):
                queue.append(parts.path + (f"?{parts.query}" if parts.query else ""))
    assert not found, "\n".join(found)
