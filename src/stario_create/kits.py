"""Kits: tested files that `stario-create add <kit>` writes into an app.

Each kit is a folder in ``templates/kits/<kit>/`` at the paths of the app.
A ``*.tmpl`` file takes ``$app_name`` and loses its suffix. For each file:

- a missing file is written;
- a file that equals the scaffold version (the app never changed it) is replaced;
- any other file is kept, and the result names it for a merge by hand.

A ``justfile`` in a kit is appended once, and so are the routes in its ``app/urls.py``
(each app keeps every route in that file). The agent then reads the files,
not a skill that holds their text.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

from stario_create.data import template
from stario_create.scaffold import GENERATED_TESTS, ScaffoldError

_PACKAGE = Path(__file__).resolve().parent
_KITS = _PACKAGE / "templates" / "kits"


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
        deps=("stario>=5.9.0,<6", "litewriter>=0.3.3,<0.4"),
        create_only=("app/data.py",),
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
    "auth-password": Kit(
        help="sign-up and sign-in with an email and a password; a session cookie; tests",
        deps=("stario>=5.9.0,<6", "litewriter>=0.3.3,<0.4"),
        create_only=("app/data.py",),
        next=(
            'Pages for signed-in users: app.use("/editor", session.require) in app/main.py; '
            "a handler behind it reads signed_in_user(c), any other current_user(c) (id or None).",
            "User columns go in CREATE TABLE users in app/auth/data.py. app/pages/login.py is plain "
            "forms: change paths (app/urls.py), labels and markup to fit; keep the route and field "
            "names, and tests/test_login.py still holds.",
            "Over plain HTTP on a laptop (not localhost), put APP_DEV=1 in .env.",
            "On a server, set SESSION_SECRET (32+ random characters); else data/session.key holds it.",
        ),
    ),
    "tailwind": Kit(
        help="Tailwind v4 and DaisyUI through the standalone binary, with a theme switch",
        gitignore=("tailwindcss", "frontend/daisyui*.mjs"),
        create_only=("static/css/output.css",),
        next=(
            "Run `just css` after a class change (`just css-watch` next to `just dev`); commit "
            "static/css/output.css. It scans app/**/*.py: write whole class names, never build them.",
            'Classes go in classes(...) or {"class": ...}; DaisyUI components (btn, card, navbar) '
            'work as is. A theme switch: h.Button(data.on("click", "app.theme.toggle()"), ...).',
        ),
    ),
    "browser": Kit(
        help="scripts/browser.py: the rare Playwright check for client JS that holds state",
        next=(
            "uv run --with playwright playwright install chromium",
            "uv run --with playwright python scripts/browser.py /your-page",
        ),
    ),
    "pages": Kit(help="tests/test_pages.py and its generated helpers: the page check and the lint"),
}

# The scaffold version of each file a kit may replace.
_SCAFFOLD: dict[str, tuple[str, ...]] = {
    "app/config.py": ("app/config.py.tmpl",),
    "app/main.py": ("app/main.py.tmpl", "app/main_db.py.tmpl"),
    "app/layout.py": ("app/layout.py.tmpl",),
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
        return [
            ("tests/test_pages.py", template("tests/test_pages.py")),
            *((rel, _PACKAGE / src) for rel, src in GENERATED_TESTS.items()),
        ]
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
        if rel == "app/urls.py" and dest.is_file():
            current = dest.read_text()
            block = text.split("\n\n", 1)[1]  # the routes, without the import
            first = next(line for line in block.splitlines() if "Route(" in line)
            if first not in current.splitlines():
                dest.write_text(current.rstrip("\n") + "\n\n" + block)
                added.written.append(rel)
            continue
        if dest.is_file():
            current = dest.read_text()
            if name == "pages" and current != text:
                dest.write_text(text)  # generated files: never edited by hand
                added.written.append(rel)
                continue
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
