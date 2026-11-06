"""Kits: tested files that `stario-create add <kit>` writes into an app.

Each kit is a folder in ``templates/kits/<kit>/`` at the paths of the app.
A ``*.tmpl`` file takes ``$app_name`` and loses its suffix. For each file:

- a missing file is written;
- a file that equals the scaffold version (the app never changed it) is replaced;
- any other file is kept, and the result names it for a merge by hand.

A ``justfile`` in a kit is appended once. The agent then reads the files,
not a skill that holds their text.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

from stario_create.data import template
from stario_create.scaffold import ScaffoldError

_KITS = Path(__file__).resolve().parent / "templates" / "kits"


@dataclass(frozen=True, slots=True)
class Kit:
    help: str
    deps: tuple[str, ...] = ()
    gitignore: tuple[str, ...] = ()
    # Written only when missing; never a merge (a built file, a placeholder).
    create_only: tuple[str, ...] = ()
    next: tuple[str, ...] = ()


KITS: dict[str, Kit] = {
    "auth": Kit(
        help="sign-in with Google and GitHub through OAuth; a session cookie; tests",
        # SignedCookie is new in stario 5.4.0.
        deps=("stario>=5.4.0,<6", "litewriter>=0.3.2,<0.4"),
        next=(
            'Set SESSION_SECRET in .env: python -c "import secrets; print(secrets.token_urlsafe(48))"',
            "Create an OAuth client at each provider (Google: Google Auth Platform, Clients, Web).",
            "Register its callback: https://<host>/login/<provider>/callback, and "
            "http://127.0.0.1:8000/login/<provider>/callback for the laptop (open that host).",
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or the GITHUB_ pair, in .env.",
            "Put APP_DEV=1 in .env on a laptop, so the cookies and the callback work over plain HTTP.",
            'Protect pages under /app, or add app.use("/todos", session.require).',
        ),
    ),
    "tailwind": Kit(
        help="Tailwind v4 and DaisyUI through the standalone binary, with a theme switch",
        gitignore=("tailwindcss", "frontend/daisyui*.mjs"),
        create_only=("static/css/output.css",),
        next=("Run `just css`, then commit static/css/output.css.",),
    ),
    "browser": Kit(
        help="scripts/browser.py: the rare Playwright check for client JS that holds state",
        next=(
            "uv run --with playwright playwright install chromium",
            "uv run --with playwright python scripts/browser.py /your-page",
        ),
    ),
    "pages": Kit(help="tests/test_pages.py: the page check that replaces a browser for HTML"),
}

# The scaffold version of each file a kit may replace.
_SCAFFOLD: dict[str, tuple[str, ...]] = {
    "app/config.py": ("app/config.py.tmpl",),
    "app/main.py": ("app/main.py.tmpl",),
    "app/assets.py": ("app/assets.py.tmpl",),
    "app/common/shell.py": ("app/common/shell.py.tmpl",),
    "tests/conftest.py": ("tests/conftest.py.tmpl",),
}


@dataclass(slots=True)
class Added:
    written: list[str] = field(default_factory=list[str])
    merge: list[tuple[str, Path]] = field(default_factory=list[tuple[str, Path]])
    deps: tuple[str, ...] = ()
    next: tuple[str, ...] = ()


def _app_name(root: Path) -> str:
    path = root / "pyproject.toml"
    if not path.is_file():
        raise ScaffoldError(
            "no-app", f"{root} has no pyproject.toml", "run `add` in the root of a Stario app"
        )
    with path.open("rb") as f:
        return str(tomllib.load(f).get("project", {}).get("name", root.name))


def _scaffold_versions(rel: str, app_name: str) -> set[str]:
    versions: set[str] = set()
    for name in _SCAFFOLD.get(rel, ()):
        text = Template(template(name).read_text())
        if rel == "app/main.py":
            versions.add(text.safe_substitute(orjson_import="", json_import="", codec=""))
            versions.add(
                text.safe_substitute(
                    orjson_import="\nimport orjson",
                    json_import=", json",
                    codec="    json.set_codec(orjson.dumps, orjson.loads)\n",
                )
            )
        else:
            versions.add(text.safe_substitute(app_name=app_name))
    return versions


def kit_files(name: str) -> list[tuple[str, Path]]:
    """(path in the app, bundled file) for each file of the kit."""
    if name == "pages":
        return [("tests/test_pages.py", template("tests/test_pages.py"))]
    base = _KITS / name
    out: list[tuple[str, Path]] = []
    for src in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = src.relative_to(base).as_posix().removesuffix(".tmpl")
        out.append((rel, src))
    return out


def add_kit(root: Path, name: str) -> Added:
    if name not in KITS:
        raise ScaffoldError(
            "no-kit", f"there is no kit '{name}'", "kits: " + ", ".join(sorted(KITS))
        )
    kit = KITS[name]
    app_name = _app_name(root)
    added = Added(deps=kit.deps, next=kit.next)
    for rel, src in kit_files(name):
        text = src.read_text()
        if src.suffix == ".tmpl":
            text = Template(text).safe_substitute(app_name=app_name)
        dest = root / rel
        if rel == "justfile":
            current = dest.read_text() if dest.is_file() else ""
            first = next(line for line in text.splitlines() if line and line[0].isalpha())
            if first not in current.splitlines():
                dest.write_text(current.rstrip("\n") + "\n" + text)
                added.written.append(rel)
            continue
        if dest.is_file():
            current = dest.read_text()
            if current == text or rel in kit.create_only:
                continue
            if current not in _scaffold_versions(rel, app_name):
                added.merge.append((rel, src))
                continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        added.written.append(rel)
    gitignore = root / ".gitignore"
    lines = gitignore.read_text().splitlines() if gitignore.is_file() else []
    missing = [line for line in kit.gitignore if line not in lines]
    if missing:
        gitignore.write_text("\n".join([*lines, *missing]) + "\n")
        added.written.append(".gitignore")
    return added
