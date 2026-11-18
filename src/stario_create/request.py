"""`stario-create request`: send requests to the app through TestClient; start no server.

The CLI runs this file with `uv run python` in the app, so it imports the app's own
`app.main.bootstrap` and its stario. It needs only the standard library and stario.

    stario-create request GET /todos
    stario-create request POST /todos -j '{"title": "milk"}' GET /todos/live

A step is METHOD PATH, then its options:
  -j JSON   a Datastar action: JSON signals and the datastar-request header
  -s JSON   signals on a GET (?datastar=...), with the datastar-request header
  -d k=v    a plain form field (repeat it)
  -H k:v    a header (repeat it)
Every step shares one client, so a cookie from a sign-in reaches the next step.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "QUERY", "OPTIONS"})


@dataclass(slots=True)
class Step:
    method: str
    path: str
    json: Any = None
    signals: str | None = None
    form: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


class Usage(Exception):
    pass


def parse_steps(argv: list[str]) -> list[Step]:
    steps: list[Step] = []
    args = list(argv)
    while args:
        word = args.pop(0)
        if word.upper() in METHODS:
            if not args:
                raise Usage(f"{word} needs a path, e.g. `{word.upper()} /`")
            steps.append(Step(word.upper(), args.pop(0)))
            continue
        if not steps:
            raise Usage(f"start with METHOD PATH, not {word!r}")
        if word not in ("-j", "-s", "-d", "-H") or not args:
            raise Usage(f"unknown option {word!r}: use -j JSON, -s JSON, -d k=v, -H k:v")
        value, step = args.pop(0), steps[-1]
        if word == "-j":
            step.json = json.loads(value)
            step.headers["datastar-request"] = "true"
        elif word == "-s":
            json.loads(value)
            step.signals = value
            step.headers["datastar-request"] = "true"
        elif word == "-d":
            key, _, val = value.partition("=")
            step.form[key] = val
        else:
            key, _, val = value.partition(":")
            step.headers[key.strip().lower()] = val.strip()
    if not steps:
        raise Usage("give METHOD PATH, e.g. `stario-create request GET /`")
    return steps


async def _first_events(events: AsyncIterator[dict[str, str]], wait: float) -> list[dict]:
    """Events until the stream ends, or `wait` seconds pass with no new event."""
    out: list[dict] = []
    while True:
        try:
            out.append(await asyncio.wait_for(anext(events), wait))
        except StopAsyncIteration, TimeoutError:
            return out


async def run(
    bootstrap: Callable[..., Any], steps: list[Step], wait: float = 0.5
) -> tuple[list[str], bool]:
    """The printed lines of each step, and whether every step answered below 500."""
    from stario.testing import TestClient

    lines: list[str] = []
    ok = True
    async with TestClient(bootstrap, request_timeout=10) as client:
        for step in steps:
            params = {"datastar": step.signals} if step.signals is not None else None
            async with client.stream(
                step.method,
                step.path,
                params=params,
                json=step.json,
                data=step.form or None,
                headers={"accept-encoding": "identity", **step.headers},
                timeout=10,
            ) as r:
                kind = r.headers.get("content-type", "") or ""
                lines.append(f"{step.method} {step.path} -> {r.status_code} {kind}".rstrip())
                if location := r.headers.get("location"):
                    lines.append(f"location: {location}")
                if "text/event-stream" in kind:
                    events = await _first_events(r.iter_events(), wait)
                    for event in events:
                        lines.append(f"event: {event.get('event', 'message')}")
                        lines += [f"  {row}" for row in event.get("data", "").splitlines()]
                    if not events:
                        lines.append(f"(no event in {wait}s)")
                else:
                    body = b"".join([chunk async for chunk in r.iter_bytes()])
                    if body:
                        lines.append(body.decode("utf-8", "replace"))
            if r.status_code >= 500:
                ok = False
                span = client.tracer.get_span(r.span_id) if r.span_id else None
                for event in span.events if span else ():
                    if event.name == "exception":
                        exc = event.attributes
                        lines.append(f"error: {exc.get('exc.type')}: {exc.get('exc.message')}")
    return lines, ok


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines of .env into the environment, as `just` does; a set variable wins."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main(argv: list[str]) -> int:
    root = Path.cwd()
    try:
        steps = parse_steps(argv)
    except (Usage, ValueError) as e:
        print(f"stario-create request: {e}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(root))
    load_dotenv(root / ".env")
    with tempfile.TemporaryDirectory() as data:
        # A fresh data dir: the app's own database (and a dev server's claim) stays untouched.
        os.environ["PROJECT_DATA_DIR"] = data
        os.environ.pop("DATABASE_PATH", None)
        bootstrap = importlib.import_module("app.main").bootstrap
        lines, ok = asyncio.run(run(bootstrap, steps))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
