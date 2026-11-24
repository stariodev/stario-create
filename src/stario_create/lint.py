"""Stario rules that ruff and pyrefly do not check. Each finding states the fix.

`stario-create` writes a copy of this file into each app as `tests/_lint.py`, and
`tests/test_pages.py` runs it, so `just check` and `stario-create check` report
the rules. It needs only the standard library. `# stario: ok` on a line skips it.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TIME_KEYWORDS = frozenset({"debounce", "delay", "throttle"})
DATASTAR_NAMES = frozenset({"at", "data", "SSE", "read_signals", "ModuleScript", "FileSignal"})
STATE_CALLS = frozenset(
    {
        "list",
        "dict",
        "set",
        "defaultdict",
        "deque",
        "OrderedDict",
        "Counter",
        "Relay",
        "LiteWriter",
        "Queue",
        "Lock",
        "Event",
        "Semaphore",
        "AsyncClient",
        "Client",
    }
)
SHELL_FILES = ("justfile", "Makefile", "package.json", "Procfile")
KILL = re.compile(r"\b(pkill\s+-f|killall)\b")
ORDER_BY_PARAM = re.compile(r"\bORDER\s+BY\s+:\w", re.I)
SKIP = "# stario: ok"


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


def _dotted(node: ast.expr) -> str:
    """`a.b.c` for a Name or Attribute chain, else ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, config: bool) -> None:
        self.path = path
        self.config = config
        self.found: list[Finding] = []
        self.loops = 0

    def add(self, node: ast.AST, rule: str, message: str) -> None:
        self.found.append(Finding(self.path, getattr(node, "lineno", 1), rule, message))

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "redirect"
            and len(node.args) == 1
            and not node.keywords
        ):
            self.add(
                node,
                "redirect-status",
                f"{name}(url) answers 307, which repeats a POST; pass the status: "
                f"{name}(url, 303) after a form post (a Datastar action: SSE(w).navigate(url))",
            )
        for kw in node.keywords:
            value = kw.value
            if (
                kw.arg in TIME_KEYWORDS
                and isinstance(value, ast.Constant)
                and isinstance(value.value, (int, float))
                and not isinstance(value.value, bool)
                and value.value >= 10
            ):
                self.add(
                    value,
                    "time-unit",
                    f'{kw.arg}={value.value} is {value.value} seconds; write {kw.arg}="'
                    f'{value.value:g}ms" (a number is seconds)',
                )
        if name in ("os.getenv", "os.environ.get", "getenv", "environ.get") and not self.config:
            self.add(
                node,
                "env-outside-config",
                "read settings in app/config.py: add a Config field with a default "
                "(from_env reads FIELD_NAME), build Config in bootstrap, pass the value on",
            )
        if name in ("asyncio.create_task", "asyncio.ensure_future"):
            self.add(
                node,
                "bare-task",
                "use c.app.create_task(coro) (or app.create_task in bootstrap): Stario "
                "tracks the task and waits for it on shutdown",
            )
        if name == "asyncio.sleep" and self.loops:
            self.add(
                node,
                "sleep-loop",
                "a loop on a timer waits on shutdown, not asyncio.sleep: read "
                "`shutdown = app.shutdown` once, then `await asyncio.wait({shutdown}, "
                "timeout=interval)`; a stream loops on c.alive(source)",
            )
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for value in node.values:
            if isinstance(value, ast.Call) and _dotted(value.func) == "classes":
                self.add(
                    value,
                    "classes-in-dict",
                    "classes(...) is an attribute of its own, not a dict value: "
                    'h.Div(classes("a", {"b": on}), {"id": "x"}, ...)',
                )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and ORDER_BY_PARAM.search(node.value):
            self.add(
                node,
                "order-by-param",
                "ORDER BY takes no :parameter (it sorts by a constant); pick the SQL text "
                'from a dict of fixed orders: SORTS = {"new": "created DESC", ...}',
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _dotted(node) == "os.environ" and not self.config:
            self.add(
                node,
                "env-outside-config",
                "read settings in app/config.py: add a Config field with a default "
                "(from_env reads FIELD_NAME), build Config in bootstrap, pass the value on",
            )
            return
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.loops += 1
        self.generic_visit(node)
        self.loops -= 1

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "stario":
            wrong = sorted(a.name for a in node.names if a.name in DATASTAR_NAMES)
            if wrong:
                self.add(
                    node,
                    "datastar-import",
                    f"import {', '.join(wrong)} from stario.datastar, not from stario",
                )
        if node.module == "json":
            self.add(node, "json-module", "use `from stario.json import dumps, loads`")

    def visit_Import(self, node: ast.Import) -> None:
        if any(a.name == "json" for a in node.names):
            self.add(node, "json-module", "use `from stario.json import dumps, loads`")

    def visit_Global(self, node: ast.Global) -> None:
        self.add(
            node,
            "module-state",
            "no global state: keep it in an object built in bootstrap and passed to "
            "the page class (a field), so each test and each app gets its own",
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._redirect_after_signals(node)
        loops, self.loops = self.loops, 0
        self.generic_visit(node)
        self.loops = loops

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._redirect_after_signals(node)
        loops, self.loops = self.loops, 0
        self.generic_visit(node)
        self.loops = loops

    def _redirect_after_signals(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        calls = [_dotted(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)]
        if "read_signals" not in calls:
            return
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and (
                _dotted(n.func).endswith(".redirect") or _dotted(n.func) == "RedirectException"
            ):
                self.add(
                    n,
                    "redirect-after-signals",
                    "a Datastar action follows no redirect: answer SSE(w).navigate(url); "
                    "w.redirect is for a plain <form method=post>",
                )


def _module_state(tree: ast.Module, path: str) -> Iterator[Finding]:
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            value, target = stmt.value, stmt.targets[0]
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            value, target = stmt.value, stmt.target
        else:
            continue
        empty = isinstance(value, (ast.List, ast.Set)) and not value.elts
        empty = empty or (isinstance(value, ast.Dict) and not value.keys)
        call = isinstance(value, ast.Call) and _dotted(value.func).rsplit(".", 1)[-1] in (
            STATE_CALLS
        )
        if empty or call:
            name = _dotted(target) or "it"
            yield Finding(
                path,
                stmt.lineno,
                "module-state",
                f"{name} is module-level state, shared by every request and test; build it "
                "in bootstrap and pass it to the page class as a field",
            )


def lint_source(source: str, path: str) -> list[Finding]:
    """The findings of one Python file of the app (path as shown in messages)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # ruff reports it
    visitor = _Visitor(path, config=path.endswith("config.py"))
    if path.startswith("app/") or "/app/" in path:
        visitor.visit(tree)
        visitor.found.extend(_module_state(tree, path))
    lines = source.splitlines()
    found = [f for f in visitor.found if f.line > len(lines) or SKIP not in lines[f.line - 1]]
    for number, line in enumerate(lines, 1):
        if KILL.search(line) and SKIP not in line:
            found.append(Finding(path, number, "pkill", _KILL_FIX))
    return sorted(set(found), key=lambda f: (f.line, f.rule))


_KILL_FIX = (
    "pkill -f and killall stop every matching process, other apps too; stop the "
    "server you started by its port (`lsof -ti tcp:PORT | xargs kill`; `kill $!` does "
    "not reach a job of an earlier shell), or skip the server: `stario-create request GET /path`"
)


def lint(root: Path) -> list[Finding]:
    """Every finding under root: app/ and tests/ Python files, scripts, the justfile."""
    found: list[Finding] = []
    for folder in ("app", "tests", "scripts"):
        for path in sorted((root / folder).rglob("*.py")):
            if path.name == "_lint.py" or ".venv" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            found += lint_source(path.read_text(), rel)
    shell = [root / name for name in SHELL_FILES] + sorted(root.glob("scripts/*.sh"))
    for path in shell + sorted(root.glob("*.sh")):
        if path.is_file():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if KILL.search(line) and SKIP not in line:
                    rel = path.relative_to(root).as_posix()
                    found.append(Finding(rel, number, "pkill", _KILL_FIX))
    return found


def main(argv: list[str] | None = None) -> int:
    root = Path((argv or sys.argv[1:] or ["."])[0])
    found = lint(root)
    for finding in found:
        print(finding)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
