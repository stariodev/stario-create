"""`stario-create add page <name>...`: one page in one call.

For each name it writes `app/pages/<name>.py` (the class and its render), the route in
`app/urls.py`, the import and the register line in `app/main.py`, and a `LINKS` line
in `app/pages/home.py`. `name=/path/{param}` sets the URL; the default is `/<name>`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from stario_create.scaffold import ScaffoldError, check_name

_PARAM = re.compile(r"\{(\w+)(?:\.\.\.)?\}")
_LINKS_EMPTY = "LINKS: tuple[tuple[Route, str], ...] = ()"


@dataclass(slots=True)
class PageAdded:
    written: list[str] = field(default_factory=list[str])
    by_hand: list[str] = field(default_factory=list[str])


def _page_source(name: str, route: str, params: list[str], db: bool) -> str:
    cls = "".join(part.capitalize() for part in name.split("_")) + "Page"
    title = name.replace("_", " ").capitalize()
    args = ", ".join(f"{p}: str" for p in params)
    reads = "".join(f'        {p} = c.match.params["{p}"]\n' for p in params)
    call = ", ".join(params)
    lines = [
        "from dataclasses import dataclass",
        "",
        *(["from litewriter import LiteWriter"] if db else []),
        "from stario import App, Context, Writer, h",
        "from stario.markup import HtmlElement",
        "",
        "from app.layout import page",
        f"from app.urls import {route}",
        "",
        "",
        "@dataclass(frozen=True, slots=True)",
        f"class {cls}:",
        *(["    db: LiteWriter", ""] if db else []),
        "    def register(self, app: App) -> None:",
        f"        app.add({route}, self.show)",
        "",
        "    async def show(self, c: Context, w: Writer) -> None:",
        f"{reads}        w.html(render({call}))",
        "",
        "",
        f"def render({args}) -> HtmlElement:",
        f'    return page("{title}", h.Main({{"id": "{name}"}}, h.H1("{title}")))',
        "",
    ]
    return "\n".join(lines)


def _insert_after_last(text: str, pattern: str, line: str) -> str | None:
    """text with `line` after the last line that matches `pattern`, or None."""
    rows = text.splitlines(keepends=True)
    hits = [i for i, row in enumerate(rows) if re.search(pattern, row)]
    if not hits:
        return None
    last = hits[-1]
    indent = re.match(r"\s*", rows[last])
    rows.insert(last + 1, (indent.group(0) if indent else "") + line + "\n")
    return "".join(rows)


def add_page(root: Path, spec: str) -> PageAdded:
    """Add one page. `spec` is `name` or `name=/path`."""
    name, _, path = spec.partition("=")
    check_name(name)
    path = path or "/" + name.replace("_", "-")
    if not path.startswith("/"):
        raise ScaffoldError("bad-path", f"'{path}' is not a path", "write it as /rooms/{room_id}")
    urls, main, home = root / "app/urls.py", root / "app/main.py", root / "app/pages/home.py"
    target = root / "app/pages" / f"{name}.py"
    if not urls.is_file() or not main.is_file():
        raise ScaffoldError(
            "no-app",
            f"{root} has no app/urls.py and app/main.py",
            "run it at the root of an app from `stario-create new`",
        )
    if target.exists():
        raise ScaffoldError("exists", f"{target.relative_to(root)} exists", "pick another name")
    route = name.upper()
    if re.search(rf"^{route}\s*=", urls.read_text(), re.M):
        raise ScaffoldError("exists", f"app/urls.py already has {route}", "pick another name")

    params = _PARAM.findall(path)
    main_text = main.read_text()
    db = "LiteWriter(" in main_text
    cls = "".join(part.capitalize() for part in name.split("_")) + "Page"
    added = PageAdded()

    target.write_text(_page_source(name, route, params, db))
    added.written.append(f"app/pages/{name}.py")
    urls.write_text(
        urls.read_text().rstrip("\n") + f'\n\n# {name}\n{route} = Route("GET {path}")\n'
    )
    added.written.append("app/urls.py")

    new_main = _insert_after_last(
        main_text, r"^from app\.pages\.", f"from app.pages.{name} import {cls}"
    )
    if new_main is not None:
        new_main = _insert_after_last(
            new_main, r"\.register\(app\)\s*$", f"{cls}({'db' if db else ''}).register(app)"
        )
    if new_main is None:
        added.by_hand.append(f"app/main.py: import {cls} and add {cls}(db).register(app)")
    else:
        main.write_text(new_main.replace("  # noqa: F841", "") if db else new_main)
        added.written.append("app/main.py")

    if params:
        return added
    label = name.replace("_", " ").capitalize()
    home_text = home.read_text() if home.is_file() else ""
    link = f'({route}, "{label}")'
    if _LINKS_EMPTY in home_text:
        home_text = home_text.replace(_LINKS_EMPTY, _LINKS_EMPTY[:-2] + f"({link},)")
    elif re.search(r"^LINKS: .*= \(\n", home_text, re.M):
        home_text = re.sub(r"^(LINKS: .*= \(\n)", rf"\g<1>    {link},\n", home_text, flags=re.M)
    elif re.search(r"^LINKS: .*= \((.*)\)$", home_text, re.M):
        home_text = re.sub(
            r"^(LINKS: .*= \()(.*)\)$", rf"\g<1>\g<2> {link},)", home_text, count=1, flags=re.M
        )
    else:
        added.by_hand.append(f"app/pages/home.py: add {link} to LINKS")
        return added
    home_text = re.sub(
        r"^from app\.urls import (.*)$",
        rf"from app.urls import \1, {route}",
        home_text,
        count=1,
        flags=re.M,
    )
    home.write_text(home_text)
    added.written.append("app/pages/home.py")
    return added
