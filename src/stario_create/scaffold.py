"""Write project files: the app skeleton and the agent files it keeps in sync.

Templates live in ``templates/``. ``*.tmpl`` files take ``$app_name``. Cloud Agent files are copied as they are.
``string.Template`` fills ``$app_name``. All writes are idempotent: a file that
already holds the target content counts as kept, not created.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path
from string import Template

from stario_create.data import (
    guide_text,
    profile_skills,
    resource,
    skill_files,
    skill_names,
    template,
)

STARIO_REQ = "stario>=5.8.0,<6"  # the skills are verified against 5.8
LITEWRITER_REQ = "litewriter>=0.3.3,<0.4"
DEV_REQS = ["ruff", "pyrefly", "pytest", "pytest-asyncio", "watchfiles"]

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_THIS_APP = "\n## This app"
# The kit's part of AGENTS.md sits between these lines; `sync` replaces only that part.
BEGIN = "<!-- BEGIN stario-create -->"
END = "<!-- END stario-create -->"
_GUIDE_TITLE = "# Stario app guide"
_PACKAGE = Path(__file__).resolve().parent
# Tool-owned test files: written by `new` and `add pages`, refreshed by `sync`.
GENERATED_TESTS = {
    "tests/_pagecheck.py": "templates/tests/_pagecheck.py",
    "tests/_lint.py": "lint.py",
}
# Skills of earlier kits: `sync` removes them, so an app does not keep two guides to one topic,
# unless a file in one differs from every released copy (`retired_skills.json`): then it is kept.
RETIRED_SKILLS = (
    "stario-api",
    "stario-auth",
    "stario-browser-check",
    "stario-client",
    "stario-datastar",
    "stario-feature",
    "stario-jobs",
    "stario-litewriter",
    "stario-relay",
    "stario-tailwind-daisyui",
    "stario-view",
)


def _edited_retired(agents_dir: Path, name: str) -> bool:
    """True when a file under a retired skill differs from every copy a release shipped."""
    if name not in RETIRED_SKILLS or not agents_dir.is_dir():
        return False
    shipped = set(json.loads(RETIRED_TABLE.read_text()).get(name, []))
    return any(
        hashlib.sha256(f.read_bytes()).hexdigest() not in shipped
        for f in agents_dir.rglob("*")
        if f.is_file()
    )


_RULE_LIMIT = 16_000  # Devin and others cut an always-on rule file here
_NOTES_LIMIT = 4_000  # the `## This app` notes; past this, move a topic to its own file
_VENDOR = Path(__file__).resolve().parent / "vendor"
RETIRED_TABLE = Path(__file__).resolve().parent / "retired_skills.json"


class ScaffoldError(Exception):
    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint


def profile(root: Path) -> str:
    """The app profile: `[tool.stario-create] profile` in pyproject.toml.

    Defaults to "app". Any value other than "app" or "api" is an error.
    """
    path = root / "pyproject.toml"
    value = "app"
    if path.is_file():
        with path.open("rb") as f:
            value = tomllib.load(f).get("tool", {}).get("stario-create", {}).get("profile", "app")
    if value not in ("app", "api"):
        raise ScaffoldError(
            "bad-profile",
            f"[tool.stario-create] profile is '{value}'",
            'use "app" or "api"',
        )
    return value


def check_name(name: str) -> None:
    if not NAME_RE.fullmatch(name):
        raise ScaffoldError(
            "bad-name",
            f"'{name}' is not a valid feature name",
            "use lowercase snake_case, e.g. my_board",
        )


def _write(path: Path, text: str, created: list[str], *, force: bool = False) -> None:
    if path.exists():
        if path.read_text() == text:
            return
        if not force:
            raise ScaffoldError(
                "exists",
                f"{path} exists with different content",
                "pass --force to overwrite",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    created.append(str(path))


def _fill(name: str, **subs: str) -> str:
    return Template(template(name).read_text()).safe_substitute(subs)


def app_name_for(root: Path) -> str:
    """A snake_case app name from a directory name: `My App` -> `my_app`."""
    name = re.sub(r"[^a-z0-9_]+", "_", root.resolve().name.lower()).strip("_") or "app"
    return name if name[0].isalpha() else f"app_{name}"


def guide_above(root: Path) -> Path | None:
    """An AGENTS.md above root that already is the Stario guide, else None.

    An app scaffolded inside a repo whose root has the guide (and the skills)
    gets no second copy: the agent already reads the one above.
    """
    for parent in root.resolve().parents:
        path = parent / "AGENTS.md"
        if path.is_file():
            text = path.read_text()
            if BEGIN in text or text.startswith(_GUIDE_TITLE):
                return path
    return None


def generated_text(rel: str) -> str:
    """The text of a tool-owned test file: 'tests/_pagecheck.py' or 'tests/_lint.py'."""
    return (_PACKAGE / GENERATED_TESTS[rel]).read_text()


def sync_generated_tests(root: Path) -> list[str]:
    """Rewrite the tool-owned test files of an app that uses them. Returns the paths written."""
    pages = root / "tests" / "test_pages.py"
    if not pages.is_file() or "tests._pagecheck" not in pages.read_text():
        return []
    written: list[str] = []
    for rel in GENERATED_TESTS:
        path, text = root / rel, generated_text(rel)
        if not path.is_file() or path.read_text() != text:
            path.write_text(text)
            written.append(str(path))
    return written


def sync_claude(root: Path) -> str | None:
    """Make CLAUDE.md load AGENTS.md (`@AGENTS.md`). Returns the path, or None if current.

    Claude Code reads CLAUDE.md; the import line keeps one guide for every agent, and a
    project's own CLAUDE.md text stays below it.
    """
    path = root / "CLAUDE.md"
    text = path.read_text() if path.is_file() else ""
    if "@AGENTS.md" in text.splitlines():
        return None
    path.write_text("@AGENTS.md\n" + (f"\n{text}" if text else ""))
    return str(path)


def scaffold_files(
    root: Path,
    app_name: str,
    *,
    force: bool = False,
    orjson: bool = False,
    db: bool = False,
    agent_files: bool = True,
) -> list[str]:
    """Write the app tree under root. Returns the files written.

    `db` opens a litewriter database in `bootstrap`. `agent_files=False`
    skips AGENTS.md, the skills, and the Cloud Agent files.
    """
    created: list[str] = []

    def w(rel: str, text: str) -> None:
        _write(root / rel, text, created, force=force)

    w("app/__init__.py", "")
    w("app/config.py", _fill("app/config.py.tmpl", app_name=app_name))
    w("app/layout.py", _fill("app/layout.py.tmpl"))
    w("app/urls.py", _fill("app/urls.py.tmpl"))
    if db:
        w("app/data.py", _fill("app/data.py.tmpl"))
    w("app/pages/__init__.py", "")
    w("app/pages/home.py", _fill("app/pages/home.py.tmpl"))
    w(
        "app/main.py",
        _fill(
            "app/main_db.py.tmpl" if db else "app/main.py.tmpl",
            orjson_import="\nimport orjson" if orjson else "",
            json_import=", json" if orjson else "",
            codec="    json.set_codec(orjson.dumps, orjson.loads)\n" if orjson else "",
        ),
    )
    w("static/css/style.css", _fill("app/style.css.tmpl"))

    target = root / "static/js/datastar.js"
    if not target.exists() or force:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_VENDOR / "datastar.js", target)
        created.append(str(target))

    w("tests/__init__.py", "")
    w("tests/conftest.py", _fill("tests/conftest.py.tmpl"))
    w("tests/test_js.py", _fill("tests/test_js.py.tmpl"))
    w("tests/test_pages.py", template("tests/test_pages.py").read_text())
    for rel in GENERATED_TESTS:
        w(rel, generated_text(rel))

    w("justfile", template("justfile").read_text())
    w(".dockerignore", template("dockerignore").read_text())
    if agent_files:
        created.extend(sync_cloud_env(root, force=force))
        guide = sync_guide(root, force=force)
        if guide is not None:
            created.append(guide)
        claude = sync_claude(root)
        if claude is not None:
            created.append(claude)
        created.extend(sync_skill_files(root, force=force))

    _append_once(root / ".gitignore", "*.sqlite3*", created)
    _append_once(root / ".gitignore", "data/", created)
    _append_pyproject_extras(root / "pyproject.toml", created)
    return created


def link_skills(root: Path, names: Iterable[str], *, force: bool = False) -> list[str]:
    """Link .claude/skills/<name> to the copy in .agents/skills/.

    Claude Code reads skills from .claude/skills/ only. A symlink keeps one
    canonical copy; when os.symlink is unavailable the skill dir is copied.
    Returns the destination paths written.
    """
    linked: list[str] = []
    for name in names:
        dest = root / ".claude" / "skills" / name
        target = os.path.join("..", "..", ".agents", "skills", name)
        if dest.is_symlink():
            if os.readlink(dest) == target:
                continue
            dest.unlink()
        elif dest.exists():
            if not force:
                continue
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, dest, target_is_directory=True)
        except OSError:
            shutil.copytree(root / ".agents" / "skills" / name, dest)
        linked.append(str(dest))
    return linked


def _append_once(path: Path, line: str, created: list[str]) -> None:
    if path.exists() and line in path.read_text().splitlines():
        return
    with path.open("a") as f:
        f.write(line + "\n")
    if str(path) not in created:
        created.append(str(path))


def _append_pyproject_extras(path: Path, created: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text()
    if "[tool.pyrefly]" in text or "[tool.pyright]" in text:
        return
    with path.open("a") as f:
        f.write(template("pyproject_extras.toml").read_text())
    created.append(str(path))


_CLOUD_ENV_JSON = ".cursor/environment.json"
_CLOUD_INSTALL = ".cursor/cloud-install.sh"
_CLOUD_FILES = (_CLOUD_ENV_JSON, _CLOUD_INSTALL)


def sync_cloud_env(root: Path, *, force: bool = False) -> list[str]:
    """Write the Cloud Agent install files.

    environment.json is created only when missing: a saved snapshot id must
    survive sync. cloud-install.sh is tool-owned, so sync rewrites it whenever
    the content differs — no force needed.
    """
    written: list[str] = []
    env = root / _CLOUD_ENV_JSON
    if not env.is_file():
        env.parent.mkdir(parents=True, exist_ok=True)
        env.write_text(template("cursor/environment.json").read_text())
        written.append(str(env))
    install = root / _CLOUD_INSTALL
    text = template("cursor/cloud-install.sh").read_text()
    if not install.is_file() or install.read_text() != text:
        install.parent.mkdir(parents=True, exist_ok=True)
        install.write_text(text)
        written.append(str(install))
    return written


def sync_guide(root: Path, *, force: bool = False) -> str | None:
    """Write the bundled guide to AGENTS.md. Returns the path, or None if current.

    An existing file keeps everything from its `## This app` heading on. A file
    without that section needs `force`.
    """
    path = root / "AGENTS.md"
    bundled = guide_text(profile(root))
    kit = bundled[: bundled.index(END) + len(END)]
    if path.exists():
        text = path.read_text()
        if BEGIN in text and END in text:
            target = text[: text.index(BEGIN)] + kit + text[text.index(END) + len(END) :]
        elif _THIS_APP in text:
            target = bundled.split(_THIS_APP)[0] + _THIS_APP + text.split(_THIS_APP, 1)[1]
        elif force:
            target = bundled
        else:
            raise ScaffoldError(
                "no-this-app",
                "AGENTS.md has no '## This app' section",
                "pass --force to overwrite the whole file",
            )
        if text == target:
            return None
    else:
        target = bundled
    path.write_text(target)
    return str(path)


def sync_skill_files(root: Path, *, force: bool = False) -> list[str]:
    """Copy the profile's skills to .agents/skills/ and link .claude/skills/.

    A bundled skill the profile excludes is removed: its .agents/skills/<name>
    directory and the .claude/skills/<name> link, reported as
    ``removed .agents/skills/<name>``. A skill directory whose name is not
    bundled is never touched.
    """
    written: list[str] = []
    wanted = profile_skills(profile(root))
    for name in wanted:
        files = skill_files(name)
        for rel in files:
            dest = root / ".agents" / "skills" / name / rel
            text = resource(f"skills/{name}/{rel}").read_text()
            if dest.is_file() and dest.read_text() == text:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            written.append(str(dest))
        refs = root / ".agents" / "skills" / name / "references"
        for old in sorted(refs.glob("*.md")) if refs.is_dir() else []:
            if f"references/{old.name}" not in files:
                old.unlink()
                written.append(f"removed {old.relative_to(root).as_posix()}")
    written.extend(link_skills(root, wanted, force=force))
    for name in [*skill_names(), *RETIRED_SKILLS]:
        if name in wanted:
            continue
        agents_dir = root / ".agents" / "skills" / name
        link = root / ".claude" / "skills" / name
        if not agents_dir.exists() and not link.is_symlink() and not link.exists():
            continue
        if _edited_retired(agents_dir, name):
            written.append(
                f"kept .agents/skills/{name} (retired, but edited here: delete it by hand)"
            )
            continue
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)
        if agents_dir.is_dir():
            shutil.rmtree(agents_dir)
        elif agents_dir.exists():
            agents_dir.unlink()
        written.append(f"removed .agents/skills/{name}")
    return written


def _git_ignored(root: Path, skills: Iterable[str]) -> list[str]:
    """Agent files that git ignores. Empty when root is not a work tree."""
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []  # no git
    if inside.returncode != 0:
        return []
    paths = ["AGENTS.md", *_CLOUD_FILES]
    for name in skills:
        paths.append(f".agents/skills/{name}/SKILL.md")
        paths.append(f".claude/skills/{name}")
    ignored: list[str] = []
    for rel in paths:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--", rel],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            ignored.append(rel)
        # 1: not ignored. 128 (a path beyond a symlink, and other fatal
        # errors): skip the path, do not crash.
    return [f"{rel} (ignored by git)" for rel in ignored]


def _check_recipe(root: Path) -> list[str] | None:
    """The lines of the `check` recipe in root/justfile, or None without a justfile."""
    path = root / "justfile"
    if not path.is_file():
        return None
    body: list[str] | None = None
    for line in path.read_text().splitlines():
        if body is not None:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            body.append(line)
        elif line.startswith("check:"):
            body = []
    return body or []


def notes_warning(root: Path) -> str | None:
    """A warning when the `## This app` notes outgrow their budget, else None."""
    path = root / "AGENTS.md"
    if not path.is_file():
        return None
    _, sep, notes = path.read_text().partition(_THIS_APP)
    size = len((sep + notes).encode())
    if not sep or size <= _NOTES_LIMIT:
        return None
    return (
        f"AGENTS.md: '## This app' is {size} bytes (budget {_NOTES_LIMIT}); "
        "move a deep note on one topic to its own file and name it in one line"
    )


def stale_files(root: Path) -> list[str]:
    """Paths that differ from the bundle. Empty means the app is in sync."""
    stale: list[str] = []
    prof = profile(root)
    bundled = guide_text(prof)
    path = root / "AGENTS.md"
    local = path.read_text() if path.exists() else ""
    if BEGIN in local and END in local:
        current = local[local.index(BEGIN) : local.index(END)] == bundled[: bundled.index(END)]
    else:
        current = local.split(_THIS_APP)[0].strip() == bundled.split(_THIS_APP)[0].strip()
    if not current:
        stale.append("AGENTS.md")
    claude = root / "CLAUDE.md"
    if not claude.is_file() or "@AGENTS.md" not in claude.read_text().splitlines():
        stale.append("CLAUDE.md (no @AGENTS.md line)")
    if path.exists() and (size := len(path.read_bytes())) > _RULE_LIMIT:
        stale.append(f"AGENTS.md ({size} bytes; rule loaders cut at {_RULE_LIMIT})")
    if not (root / _CLOUD_ENV_JSON).is_file():
        stale.append(_CLOUD_ENV_JSON)
    install = root / _CLOUD_INSTALL
    if (
        not install.is_file()
        or install.read_text() != template("cursor/cloud-install.sh").read_text()
    ):
        stale.append(_CLOUD_INSTALL)
    wanted = profile_skills(prof)
    for name in [*skill_names(), *RETIRED_SKILLS]:
        if name not in wanted:
            agents_dir = root / ".agents" / "skills" / name
            link = root / ".claude" / "skills" / name
            if agents_dir.exists() or link.exists() or link.is_symlink():
                why = "retired" if name in RETIRED_SKILLS else f"not in profile {prof}"
                if _edited_retired(agents_dir, name):
                    why = "retired, edited here: delete it by hand"
                stale.append(f".agents/skills/{name} ({why})")
            continue
        for rel in skill_files(name):
            dest = root / ".agents" / "skills" / name / rel
            if (
                not dest.is_file()
                or dest.read_text() != resource(f"skills/{name}/{rel}").read_text()
            ):
                stale.append(f".agents/skills/{name}/{rel}")
        link = root / ".claude" / "skills" / name
        if not link.is_symlink() or os.readlink(link) != os.path.join(
            "..", "..", ".agents", "skills", name
        ):
            stale.append(f".claude/skills/{name}")
    pages = root / "tests" / "test_pages.py"
    if pages.is_file() and "tests._pagecheck" in pages.read_text():
        for rel in GENERATED_TESTS:
            gen = root / rel
            if not gen.is_file() or gen.read_text() != generated_text(rel):
                stale.append(rel)
    stale.extend(_git_ignored(root, wanted))
    check = _check_recipe(root)
    if check is not None:
        if not any("pytest" in line for line in check):
            stale.append("justfile (check does not run pytest)")
        if any("pyright" in line for line in check):
            stale.append("justfile (check runs pyright; run `uv run pyrefly check`)")
    return stale
