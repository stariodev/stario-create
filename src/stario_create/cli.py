"""stario-create command line.

`new` scaffolds an app, `add` writes a kit of tested files (or a page) into it, `sync`
refreshes its guide, skills, and generated files, `check` runs format, lint, types, and
tests, `lint` runs the Stario rules alone, and `request` sends requests through TestClient.
Output is plain text. Errors print `stario-create: <message>` to stderr, with
a `hint:` line when there is one, and exit 1.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from stario_create import TRACKS_STARIO, __version__, request
from stario_create.kits import KITS, add_kit
from stario_create.lint import lint
from stario_create.pages import add_page
from stario_create.scaffold import (
    DEV_REQS,
    LITEWRITER_REQ,
    STARIO_REQ,
    ScaffoldError,
    app_name_for,
    check_name,
    drop_claude_import,
    guide_above,
    notes_warning,
    scaffold_files,
    stale_files,
    sync_cloud_env,
    sync_generated_tests,
    sync_guide,
    sync_ruff_exclude,
    sync_skill_files,
)


def _fail(err: ScaffoldError) -> None:
    print(f"stario-create: {err}", file=sys.stderr)
    if err.hint:
        print(f"hint: {err.hint}", file=sys.stderr)


def _run(argv: list[str], cwd: Path) -> None:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ScaffoldError(
            "command-failed",
            f"`{' '.join(argv)}` failed",
            "\n".join(tail) or f"exit {proc.returncode}",
        )


# What `new` writes, printed after it so an agent need not open the files.
_NEW_SUMMARY = """\
  pyproject.toml uv.lock  stario{db_dep}; dev: ruff pyrefly pytest pytest-asyncio watchfiles
  justfile               just dev (reload) | just serve | just check | just test -k NAME
  app/config.py          Config: a field with a default per setting, read from the env
                         var of its name in capitals; data_dir from PROJECT_DATA_DIR
                         (default ./data); db_path: DATABASE_PATH, else data_dir/app.sqlite3
  static/                css/style.css (plain CSS), js/datastar.js
  tests/conftest.py      fixture `client`: TestClient(bootstrap), PROJECT_DATA_DIR=tmp_path
  tests/test_pages.py    generated: the page check and the lint (with tests/_pagecheck.py,
                         tests/_lint.py, tests/test_js.py); keep them, do not read or edit{agent_note}"""

# Printed in full before the summary: the files a new page changes, the most used last.
_NEW_FILES = ("app/layout.py", "app/pages/home.py", "app/main.py", "app/data.py", "app/urls.py")


def cmd_new(args: argparse.Namespace) -> int:
    base = Path(args.dir).expanduser() if args.dir else Path.cwd()
    dest = (base / args.path).resolve()
    app_name = args.name or app_name_for(dest)
    check_name(app_name)
    if (
        dest.exists()
        and any(dest.iterdir())
        and not dest.joinpath("pyproject.toml").exists()
        and not args.force
    ):
        raise ScaffoldError(
            "not-empty",
            f"{dest} is not empty and has no pyproject.toml",
            "scaffold into a new folder (`new app`), or pass --force to write here",
        )
    dest.mkdir(parents=True, exist_ok=True)
    above = guide_above(dest)

    if not (dest / "pyproject.toml").exists():
        _run(
            ["uv", "init", "--app", "--no-package", "--python", "3.14", "-q"],
            dest,
        )
    for leftover in ("main.py", ".python-version"):
        # requires-python pins 3.14 for uv. A .python-version also steers pyenv's
        # shims, and a bare `python3` then fails where pyenv has no 3.14.
        (dest / leftover).unlink(missing_ok=True)
    deps = [STARIO_REQ, *([LITEWRITER_REQ] if args.db else [])]
    _run(["uv", "add", "-q", *deps, *(["orjson>=3.13.0"] if args.orjson else [])], dest)
    _run(["uv", "add", "-q", "--dev", *DEV_REQS], dest)

    created = scaffold_files(
        dest,
        app_name,
        force=args.force,
        orjson=args.orjson,
        db=args.db,
        agent_files=above is None,
    )

    verified = ""
    if not args.no_verify:
        proc = subprocess.run(
            ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-10:]
            raise ScaffoldError(
                "verify-failed",
                "the new app's tests failed",
                "\n".join(tail) or f"exit {proc.returncode}",
            )
        verified = ", tests pass"

    where = os.path.relpath(dest)
    print(f"created {where}/ ({len(created)} files{verified}); app_name={app_name!r}")
    # Agents read the end of long output (`| tail -40`), so the files come first and the
    # summary and the next step last.
    for rel in _NEW_FILES:
        if (dest / rel).is_file():
            print(f"\n==> {rel} <==\n{(dest / rel).read_text().rstrip()}")
    agent_note = (
        f"\n  (no AGENTS.md or skills here: {os.path.relpath(above)} is the guide)"
        if above
        else "\n  AGENTS.md .agents/skills/ .claude/skills/ .cursor/   the guide, skills"
    )
    print(f"\n{where}/ holds the files above and:")
    print(
        _NEW_SUMMARY.format(db_dep=f" {LITEWRITER_REQ}" if args.db else "", agent_note=agent_note)
    )
    print(
        f"\nnext: cd {where}; a kit now, before any code, if the task needs it (`uvx "
        "stario-create@latest add auth --password`, `add auth`, `add tailwind`); then write "
        "urls, data, layout, pages, main in few messages; then `uvx stario-create@latest check`"
    )
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.kit is None:
        for name, kit in KITS.items():
            if name != "auth-password":
                print(f"{name:10} {kit.help}")
        print(f"{'auth --password':10} {KITS['auth-password'].help}")
        print(f"{'page NAME':10} a page: app/pages/NAME.py, its route, register line, and link")
        return 0
    root = Path.cwd()
    if args.kit == "page":
        if not args.names:
            raise ScaffoldError(
                "no-name", "add page needs a name", "e.g. `add page rooms room=/rooms/{room_id}`"
            )
        for spec in args.names:
            page = add_page(root, spec)
            print("wrote " + ", ".join(page.written))
            for line in page.by_hand:
                print(f"by hand: {line}")
        print("next: write each render() and handler in app/pages/, then `just check`")
        return 0
    if args.names:
        raise ScaffoldError("extra-args", f"`add {args.kit}` takes no names", "")
    kit_name = "auth-password" if args.kit == "auth" and args.password else args.kit
    added = add_kit(root, kit_name)
    if added.deps and not args.no_deps:
        _run(["uv", "add", *added.deps], root)
    for rel in added.written:
        print(f"wrote {rel}")
    for rel, src in added.merge:
        print(f"merge by hand: {rel} (you changed it; the kit version is {src})")
    if not added.written and not added.merge:
        print("up to date")
    for line in added.next:
        print(f"next: {line}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    root = Path.cwd()
    if warning := notes_warning(root):
        print(f"warning: {warning}", file=sys.stderr)
    if args.check:
        stale = stale_files(root)
        for item in stale:
            print(f"stale: {item}")
        return 1 if stale else 0

    changed: list[str] = []
    if sync_guide(root, force=args.force) is not None:
        changed.append("AGENTS.md")
    if (dropped := drop_claude_import(root)) is not None:
        changed.append(dropped)
    changed += [str(Path(p).relative_to(root)) for p in sync_generated_tests(root)]
    changed += [str(Path(p).relative_to(root)) for p in sync_cloud_env(root)]
    if sync_ruff_exclude(root) is not None:
        changed.append("pyproject.toml")
    changed += [
        p if p.startswith(("removed ", "kept ")) else str(Path(p).relative_to(root))
        for p in sync_skill_files(root, force=args.force)
    ]
    if changed:
        print("\n".join(changed))
    else:
        print("up to date")
    return 0


def _uv(argv: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["uv", "run", "-q", *argv], cwd=root, capture_output=True, text=True)


def _app_root() -> Path:
    root = Path.cwd()
    if not (root / "pyproject.toml").is_file():
        raise ScaffoldError(
            "no-app", f"{root} has no pyproject.toml", "run it at the root of the app"
        )
    return root


def cmd_check(args: argparse.Namespace) -> int:
    """Format, fix lint, check types, run the tests (with the Stario lint). Print problems."""
    root = _app_root()
    steps = [
        ("format", ["ruff", "format", "-q", "."]),
        ("ruff", ["ruff", "check", "-q", "--fix", "."]),
        ("pyrefly", ["pyrefly", "check"]),
        ("pytest", ["pytest", "-q", "--no-header", "-p", "no:cacheprovider"]),
    ]
    failed: list[str] = []
    summary = ""
    for name, argv in steps:
        proc = _uv(argv, root)
        out = "\n".join(
            line for line in (proc.stdout + proc.stderr).splitlines() if " INFO " not in line
        ).strip()
        if proc.returncode != 0:
            failed.append(name)
            print(out or f"{name}: exit {proc.returncode}")
        elif name == "pytest" and out:
            summary = out.splitlines()[-1]
    if failed:
        print(f"check: failed ({', '.join(failed)})")
        return 1
    print(f"check: ok ({summary})" if summary else "check: ok")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    found = lint(Path(args.path))
    for finding in found:
        print(finding)
    return 1 if found else 0


def cmd_request(args: argparse.Namespace) -> int:
    """Run request.py with the app's own python: it imports app.main and stario."""
    root = _app_root()
    source = Path(request.__file__).read_text()
    proc = subprocess.run(["uv", "run", "-q", "python", "-c", source, *args.steps], cwd=root)
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stario-create",
        description="Create a Stario app and keep its guide and skills in sync.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("new", help="create a new app in a folder (`.` for this one)")
    p.add_argument("path", help="the app folder, e.g. `app` or `.`; made if missing")
    p.add_argument("--db", action="store_true", help="add litewriter and open SQLite in bootstrap")
    p.add_argument("--name", default=None, help="app_name (default: from the folder name)")
    p.add_argument("--dir", default=None, help="parent directory of path (default: .)")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.add_argument(
        "--orjson",
        action="store_true",
        help="add orjson and set it as the stario.json codec",
    )
    p.add_argument("--no-verify", action="store_true", help="skip the post-scaffold test run")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("add", help="write a kit of tested files, or a page, into this app")
    p.add_argument("kit", nargs="?", default=None, help="the kit or `page`; omit it to list")
    p.add_argument("names", nargs="*", help="for `page`: NAME or NAME=/path/{param}, repeated")
    p.add_argument("--password", action="store_true", help="auth: email and password sign-in")
    p.add_argument("--no-deps", action="store_true", help="do not run `uv add` for the kit")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("sync", help="update AGENTS.md, skills, and missing Cloud Agent files")
    p.add_argument("--check", action="store_true", help="exit 1 when the guide or a skill is stale")
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite AGENTS.md even without a '## This app' section",
    )
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("check", help="format, fix lint, check types, run tests; print problems")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("lint", help="the Stario rules that ruff and pyrefly do not check")
    p.add_argument("path", nargs="?", default=".", help="the app root (default: .)")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser(
        "request",
        help="send requests through TestClient and print the answer; starts no server",
        description="Steps: METHOD PATH [-j JSON | -s JSON | -d k=v | -H k:v]..., repeated. "
        "-j: a Datastar action's signals; -s: signals on a GET; -d: a plain form field.",
    )
    p.add_argument("steps", nargs=argparse.REMAINDER, help="e.g. GET /todos")
    p.set_defaults(func=cmd_request)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.version:
        print(f"stario-create {__version__} (stario {TRACKS_STARIO})")
        return
    if args.command is None:
        parser.print_help()
        return
    try:
        code = args.func(args)
    except ScaffoldError as e:
        _fail(e)
        raise SystemExit(1) from e
    raise SystemExit(code)


if __name__ == "__main__":
    main()
