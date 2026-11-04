"""stario-create command line.

Three commands: `new` scaffolds an app, `add` writes a kit of tested files into it,
and `sync` refreshes its guide, skills, and Cloud Agent files.
Output is plain text. Errors print `stario-create: <message>` to stderr, with
a `hint:` line when there is one, and exit 1.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from stario_create import TRACKS_STARIO, __version__
from stario_create.kits import KITS, add_kit
from stario_create.scaffold import (
    DEV_REQS,
    STARIO_REQ,
    ScaffoldError,
    check_name,
    notes_warning,
    scaffold_files,
    stale_files,
    sync_cloud_env,
    sync_guide,
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


def cmd_new(args: argparse.Namespace) -> int:
    base = Path(args.dir).expanduser() if args.dir else Path.cwd()
    dest = base / args.name
    check_name(args.name)
    if (
        dest.exists()
        and any(dest.iterdir())
        and not dest.joinpath("pyproject.toml").exists()
        and not args.force
    ):
        raise ScaffoldError(
            "not-empty",
            f"{dest} is not empty and has no pyproject.toml",
            "pass --force to scaffold anyway",
        )
    dest.mkdir(parents=True, exist_ok=True)

    if not (dest / "pyproject.toml").exists():
        _run(["uv", "init", "--app", "--no-package", "--python", "3.14", str(dest)], dest)
    if (dest / "main.py").exists():
        (dest / "main.py").unlink()
    # requires-python pins 3.14 for uv. A .python-version also steers pyenv's
    # shims, and a bare `python3` then fails where pyenv has no 3.14.
    (dest / ".python-version").unlink(missing_ok=True)
    _run(["uv", "add", STARIO_REQ, *(["orjson>=3.13.0"] if args.orjson else [])], dest)
    _run(["uv", "add", "--dev", *DEV_REQS], dest)

    created = scaffold_files(dest, args.name, force=args.force, orjson=args.orjson)

    if not args.no_verify:
        proc = subprocess.run(
            ["uv", "run", "pytest", "-q"], cwd=dest, capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-10:]
            raise ScaffoldError(
                "verify-failed",
                "the new app's tests failed",
                "\n".join(tail) or f"exit {proc.returncode}",
            )

    print(f"created {dest} ({len(created)} files)")
    print("next:")
    print(f"  cd {dest}")
    print("  just dev                     # http://127.0.0.1:8000, reloads on change")
    print("  just check                   # lint, types, tests — before done")
    print("  Read AGENTS.md; its Which skill list names the skill for each task.")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.kit is None:
        for name, kit in KITS.items():
            print(f"{name:10} {kit.help}")
        return 0
    root = Path.cwd()
    added = add_kit(root, args.kit)
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
    changed += [str(Path(p).relative_to(root)) for p in sync_cloud_env(root)]
    changed += [
        p if p.startswith("removed ") else str(Path(p).relative_to(root))
        for p in sync_skill_files(root, force=args.force)
    ]
    if changed:
        print("\n".join(changed))
    else:
        print("up to date")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stario-create",
        description="Create a Stario app and keep its guide and skills in sync.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("new", help="create a new project")
    p.add_argument("name")
    p.add_argument("--dir", default=None, help="parent directory (default: ./<name>)")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.add_argument(
        "--orjson",
        action="store_true",
        help="add orjson and set it as the stario.json codec",
    )
    p.add_argument("--no-verify", action="store_true", help="skip the post-scaffold test run")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("add", help="write a kit of tested files into this app")
    p.add_argument("kit", nargs="?", default=None, help="the kit; omit it to list the kits")
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
