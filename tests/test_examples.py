"""Type-check and lint every Python example in AGENTS.md and the skills (pyrefly, Stario lint).

A block whose first line names a file (`# app/data.py`, `# tests/test_todos.py`) is added
to that file of a scaffolded app (`new --db`). The skills build on the files of the
AGENTS.md page. Any other block is a fragment: it runs inside an `async def` that has
`self`, `c`, `w`, `app`, `db`, `tx`, `client`, `config` (Any), and `relay`, after the common
imports and `from app.urls import *` and the like. A name a fragment leaves undefined
(a route of its own story) is no error; a wrong argument, attribute, or type is.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from stario_create.data import guide_text, resource, skill_files, skill_names
from stario_create.kits import add_kit
from stario_create.lint import lint
from stario_create.scaffold import scaffold_files

BLOCK = re.compile(r"```python\n(.*?)```", re.S)
HEADER = re.compile(r"# ((?:app|tests)/[\w/]+\.py)(?=\n|$|[ :(])")
ERROR = re.compile(r"^ERROR (\S+?):(\d+):\S+ (.*) \[([\w-]+)\]$", re.M)
KITS = {"stario-accounts": "auth-password", "stario-tests": "auth-password"}
PYREFLY = Path(sys.executable).with_name("pyrefly")

PRELUDE = """\
import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import apsw
import httpx
from litewriter import LiteWriter, Tx
from stario import App, Assets, Context, Files, Handler, RedirectException, Relay, Route
from stario import ServerConfig, Span, Writer, classes, h, serve
from stario.cookies import SignedCookie, delete_cookie, set_cookie
from stario.datastar import SSE, at, data, read_signals
from stario.datastar.format import string_literal
from stario.forms import read_form
from stario.http import catch_errors, same_origin, security_headers
from stario.json import dumps, loads
from stario.markup import Attrs, HtmlElement, SafeString, baked, render
from stario.testing import TestClient

from app.config import Config
from app.data import *
from app.layout import *
from app.urls import *
{extra}

async def _fragment(
    self: Any,
    c: Context,
    w: Writer,
    app: App,
    span: Span,
    db: LiteWriter,
    tx: Tx,
    client: TestClient,
    config: Any,
    relay: Relay[dict],
):
"""


def doc_text(name: str) -> str:
    if name == "AGENTS.md":
        return guide_text()
    return "\n".join(resource(f"skills/{name}/{rel}").read_text() for rel in skill_files(name))


def blocks(text: str) -> list[str]:
    return [textwrap.dedent(b) for b in BLOCK.findall(text)]


def _append(root: Path, rel: str, code: str) -> int:
    """Add code to root/rel; return the first line number of the added code."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text() if path.is_file() else ""
    if old and not old.endswith("\n"):
        old += "\n"
    path.write_text(old + "\n" + code)
    return old.count("\n") + 2


def build(root: Path, name: str) -> list[tuple[str, int]]:
    """Write the app for doc `name`; return (file, first line) of each part the doc owns."""
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(root, "demo", db=True, agent_files=False)
    if name in KITS:
        add_kit(root, KITS[name])
    if name != "AGENTS.md":
        for code in blocks(guide_text()):
            if m := HEADER.match(code):
                _append(root, m[1], code)
    owned: list[tuple[str, int]] = []
    extra = "from app.auth.session import *" if name in KITS else ""
    for n, code in enumerate(blocks(doc_text(name))):
        if m := HEADER.match(code):
            owned.append((m[1], _append(root, m[1], code)))
            continue
        rel = f"app/_fragment_{n}.py"
        head = PRELUDE.format(extra=extra)
        (root / rel).write_text(head + textwrap.indent(code, "    ") + "\n")
        owned.append((rel, head.count("\n") + 1))
    return owned


def problems(root: Path, owned: list[tuple[str, int]]) -> list[str]:
    proc = subprocess.run(
        [
            str(PYREFLY),
            "check",
            "--output-format",
            "min-text",
            "--python-interpreter-path",
            sys.executable,
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    starts = dict(owned)
    found = []
    for path, line, message, kind in ERROR.findall(proc.stdout + proc.stderr):
        if path not in starts or int(line) < starts[path]:
            continue  # the base app, or the scaffold's lines of a file the doc adds to
        if path.startswith("app/_fragment_") and kind in ("unknown-name", "unbound-name"):
            continue
        found.append(f"{path}:{line}: {message} [{kind}]")
    for finding in lint(root):  # the Stario lint holds for the examples too
        if finding.path in starts and finding.line >= starts[finding.path]:
            found.append(str(finding))
    return found


@pytest.mark.skipif(not PYREFLY.is_file(), reason="pyrefly is not installed")
@pytest.mark.parametrize("name", ["AGENTS.md", *skill_names()])
def test_every_example_type_checks(tmp_path: Path, name: str):
    owned = build(tmp_path, name)
    found = problems(tmp_path, owned)
    if found:
        keep = Path(__file__).resolve().parent.parent / ".examples" / name
        shutil.rmtree(keep, ignore_errors=True)
        shutil.copytree(tmp_path, keep)
    assert not found, f"{name} (the app is kept in .examples/{name}):\n" + "\n".join(found)


def test_the_agents_page_files_are_whole():
    """The AGENTS.md page files start with their imports: a copy needs nothing else.
    A block headed `# app/<file>.py (add)` holds lines to add to a scaffold file."""
    for code in blocks(guide_text()):
        m = HEADER.match(code)
        if m and not code.split("\n", 1)[0].endswith("(add)"):
            body = code.split("\n", 1)[1]
            assert body.startswith(("from ", "import ")), m[1]
