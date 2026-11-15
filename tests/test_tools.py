"""The tools that replace prose rules: lint, request, add page, add auth --password,
the page check that skips an outside service, and the generated files that sync keeps."""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import stario_create.lint as lint_module
from stario_create.data import skill_files, skill_names
from stario_create.kits import add_kit
from stario_create.lint import lint, lint_source
from stario_create.pages import add_page
from stario_create.request import Step, Usage, parse_steps, run
from stario_create.scaffold import (
    BEGIN,
    END,
    GENERATED_TESTS,
    ScaffoldError,
    generated_text,
    scaffold_files,
    stale_files,
    sync_claude,
    sync_generated_tests,
    sync_guide,
    sync_skill_files,
)

CLI = [sys.executable, "-m", "stario_create.cli"]


def rules(source: str, path: str = "app/pages/x.py") -> list[str]:
    return [f.rule for f in lint_source(source, path)]


def app_tests(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the app's own tests with this interpreter (it has stario and litewriter)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def app(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(tmp_path, "demo", db=True, agent_files=False)
    return tmp_path


# --- lint -------------------------------------------------------------------


def test_lint_attrs_after_children():
    assert rules('h.I({"class": "x"}, "child", data.on("click", "x"))') == ["attrs-after-children"]
    assert rules('h.Li("a", classes("tag"))') == ["attrs-after-children"]
    assert rules('h.Div(h.P("a"), {"id": "x"})') == ["attrs-after-children"]
    assert rules('h.Ul({"id": "x"}, data.show("$x"), *[h.Li(t) for t in ts])') == []
    assert rules('h.A(classes("b"), {"href": u}, label, icon)') == []


def test_lint_time_unit():
    found = lint_source('data.on("input", x, debounce=300)', "app/pages/x.py")
    assert [f.rule for f in found] == ["time-unit"]
    assert 'debounce="300ms"' in found[0].message
    assert rules("data.init(x, delay=500)") == ["time-unit"]
    assert rules('data.on("input", x, debounce="300ms", throttle=0.3, delay=2)') == []


def test_lint_module_state():
    assert rules("CACHE = {}\nSEEN: list[str] = []\nRELAY = Relay()\n") == ["module-state"] * 3
    assert rules('SORTS = ("a", "b")\nSQL = {"new": "SELECT 1"}\nLINKS = ()\n') == []
    assert rules("def f():\n    global X\n") == ["module-state"]


def test_lint_env_outside_config():
    assert rules('import os\nx = os.environ.get("X")\ny = os.getenv("Y")\n') == [
        "env-outside-config",
        "env-outside-config",
    ]
    assert rules('import os\nx = os.environ.get("X")\n', "app/config.py") == []


def test_lint_datastar_import_json_and_tasks():
    assert rules("from stario import App, at, data\n") == ["datastar-import"]
    assert rules("import json\n") == ["json-module"]
    assert rules("import asyncio\nasyncio.create_task(f())\n") == ["bare-task"]
    loop = "import asyncio\nasync def f():\n    while True:\n        await asyncio.sleep(5)\n"
    assert rules(loop) == ["sleep-loop"]
    assert rules("import asyncio\nasync def f():\n    await asyncio.sleep(1)\n") == []


def test_lint_redirect_after_signals():
    handler = (
        "async def add(self, c, w):\n"
        "    s = await read_signals(c.req)\n"
        "    w.redirect('/', status=303)\n"
    )
    assert rules(handler) == ["redirect-after-signals"]
    assert rules(handler.replace("read_signals", "read_form")) == []


def test_lint_pkill_anywhere_and_the_skip_comment(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/a.py").write_text("CACHE = {}  # stario: ok\nX = []\n")
    (tmp_path / "justfile").write_text("stop:\n    pkill -f app.main\n")
    found = [(f.path, f.line, f.rule) for f in lint(tmp_path)]
    assert found == [("app/a.py", 2, "module-state"), ("justfile", 2, "pkill")]
    assert "kill $!" in lint(tmp_path)[1].message


def test_lint_outside_app_checks_only_pkill():
    assert rules("CACHE = {}\nimport json\n", "tests/test_x.py") == []


def test_lint_cli_exits_1_and_prints_the_fix(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/a.py").write_text("CACHE = {}\n")
    out = subprocess.run([*CLI, "lint", str(tmp_path)], capture_output=True, text=True)
    assert out.returncode == 1
    assert out.stdout.startswith("app/a.py:1: module-state: CACHE is module-level state")


def test_every_scaffold_and_kit_file_passes_the_lint(app: Path):
    for kit in ("auth-password", "tailwind", "browser"):
        add_kit(app, kit)
    assert lint(app) == []


def test_the_app_gets_the_lint_and_the_page_check_as_generated_files(app: Path):
    for rel in GENERATED_TESTS:
        assert (app / rel).read_text() == generated_text(rel)
    assert (app / "tests/_lint.py").read_text() == Path(lint_module.__file__).read_text()
    assert "tests._lint" in (app / "tests/test_pages.py").read_text()


# --- the page check and the scaffold's own tests ---------------------------------


def test_the_new_app_passes_its_own_tests(app: Path):
    out = app_tests(app)
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_lint_fails_the_app_tests(app: Path):
    (app / "app/state.py").write_text("SEEN = []\n")
    out = app_tests(app)
    assert out.returncode == 1
    assert "app/state.py:1: module-state" in out.stdout


def test_the_page_check_skips_a_page_whose_service_is_down(app: Path):
    home = app / "app/pages/home.py"
    home.write_text(
        home.read_text()
        .replace("import dataclass\n", "import dataclass\n\nimport httpx\n", 1)
        .replace(
            "        w.html(render(self.app_name))",
            "        async with httpx.AsyncClient() as http:\n"
            '            await http.get("http://127.0.0.1:9/")\n'
            "        w.html(render(self.app_name))",
        )
    )
    out = app_tests(app, "-rs", "tests/test_pages.py")
    assert out.returncode == 0, out.stdout
    assert "needs a service that is not running (ConnectError" in out.stdout


def test_the_page_check_reports_a_page_that_fails(app: Path):
    home = app / "app/pages/home.py"
    home.write_text(home.read_text().replace("h.H1(app_name),", 'h.H1(app_name, {"id": "x"}),'))
    out = app_tests(app, "tests/test_pages.py")
    assert out.returncode == 1
    assert "/ answers 500 StarioError: HTML attributes must be passed before children" in (
        out.stdout
    )


# --- add page -------------------------------------------------------------------


def test_add_page_writes_the_page_its_route_register_line_and_link(app: Path):
    assert add_page(app, "rooms").by_hand == []
    assert add_page(app, "room=/rooms/{room_id}").by_hand == []
    urls = (app / "app/urls.py").read_text()
    assert 'ROOMS = Route("GET /rooms")' in urls
    assert 'ROOM = Route("GET /rooms/{room_id}")' in urls
    main = (app / "app/main.py").read_text()
    assert "from app.pages.rooms import RoomsPage" in main
    assert "        RoomsPage(db).register(app)\n        RoomPage(db).register(app)" in main
    assert "noqa" not in main
    home = (app / "app/pages/home.py").read_text()
    assert '(ROOMS, "Rooms")' in home
    assert "ROOM," not in home
    assert 'room_id = c.match.params["room_id"]' in (app / "app/pages/room.py").read_text()
    out = app_tests(app)
    assert out.returncode == 0, out.stdout + out.stderr


def test_add_page_refuses_a_page_that_exists(app: Path):
    add_page(app, "rooms")
    with pytest.raises(ScaffoldError):
        add_page(app, "rooms")
    with pytest.raises(ScaffoldError):
        add_page(app, "Bad-Name")


def test_add_page_without_db(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(tmp_path, "demo", agent_files=False)
    add_page(tmp_path, "about")
    assert "AboutPage().register(app)" in (tmp_path / "app/main.py").read_text()
    assert "LiteWriter" not in (tmp_path / "app/pages/about.py").read_text()
    out = app_tests(tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr


def test_cli_add_page_takes_several_names(app: Path):
    out = subprocess.run(
        [*CLI, "add", "page", "articles", "article=/article/{slug}"],
        cwd=app,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert "wrote app/pages/articles.py" in out.stdout
    assert (app / "app/pages/article.py").is_file()


# --- add auth --password --------------------------------------------------------------


@pytest.mark.parametrize("db", [True, False])
def test_password_auth_kit_passes_its_tests(tmp_path: Path, db: bool):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(tmp_path, "demo", db=db, agent_files=False)
    added = add_kit(tmp_path, "auth-password")
    assert added.merge == []
    assert 'SIGN_UP = Route("POST /signup")' in (tmp_path / "app/urls.py").read_text()
    out = app_tests(tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "9 passed" in out.stdout  # the page check, the lint, test_js, and 6 login tests


def test_cli_add_auth_password_picks_the_password_kit(app: Path):
    out = subprocess.run(
        [*CLI, "add", "auth", "--password", "--no-deps"], cwd=app, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "wrote app/auth/password.py" in out.stdout
    listing = subprocess.run([*CLI, "add"], cwd=app, capture_output=True, text=True).stdout
    assert "auth --password" in listing
    assert "page NAME" in listing


# --- request --------------------------------------------------------------------------


def test_parse_steps():
    steps = parse_steps(["GET", "/", "post", "/todos", "-j", '{"title": "x"}', "-H", "x-a: 1"])
    assert steps[0] == Step("GET", "/")
    assert steps[1].method == "POST"
    assert steps[1].json == {"title": "x"}
    assert steps[1].headers == {"datastar-request": "true", "x-a": "1"}
    form = parse_steps(["POST", "/login", "-d", "email=a@b.c", "-d", "next=/"])[0]
    assert form.form == {"email": "a@b.c", "next": "/"}
    for bad in ([], ["/todos"], ["GET"], ["GET", "/", "-x", "1"]):
        with pytest.raises(Usage):
            parse_steps(bad)


async def test_request_prints_html_events_redirects_and_errors(app: Path, monkeypatch):
    add_page(app, "rooms")
    monkeypatch.syspath_prepend(str(app))
    monkeypatch.setenv("PROJECT_DATA_DIR", str(app / "data"))
    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        monkeypatch.delitem(sys.modules, name)
    from app.main import bootstrap  # pyrefly: ignore[missing-import]

    lines, ok = await run(bootstrap, parse_steps(["GET", "/", "GET", "/rooms", "GET", "/nope"]))
    text = "\n".join(lines)
    assert ok
    assert "GET / -> 200 text/html" in text
    assert '<main id="rooms">' in text
    assert "GET /nope -> 404" in text


async def test_request_streams_and_commands():
    from stario import App, Context, Route, Span, Writer
    from stario.datastar import SSE, read_signals

    async def live(c: Context, w: Writer) -> None:
        sse = SSE(w)
        sse.patch_elements('<div id="x">first</div>')
        await asyncio.sleep(5)

    async def add(c: Context, w: Writer) -> None:
        title = (await read_signals(c.req)).get("title")
        SSE(w).patch_signals({"_error": f"got {title}"})

    async def broken(c: Context, w: Writer) -> None:
        raise ValueError("boom")

    async def go(c: Context, w: Writer) -> None:
        w.redirect("/there", status=303)

    async def bootstrap(app: App, span: Span):
        app.add(Route("GET /live"), live)
        app.add(Route("POST /add"), add)
        app.add(Route("GET /broken"), broken)
        app.add(Route("GET /go"), go)
        yield

    steps = parse_steps(["GET", "/live", "POST", "/add", "-j", '{"title": "milk"}', "GET", "/go"])
    lines, ok = await run(bootstrap, steps, wait=0.2)
    text = "\n".join(lines)
    assert ok
    assert "event: datastar-patch-elements" in text
    assert "first" in text
    assert "got milk" in text
    assert "location: /there" in text
    lines, ok = await run(bootstrap, parse_steps(["GET", "/broken"]))
    assert not ok
    assert "error: ValueError: boom" in "\n".join(lines)


# --- sync: references, CLAUDE.md, the marked guide, generated tests --------------------


def test_sync_copies_references_and_removes_old_ones(tmp_path: Path):
    sync_skill_files(tmp_path)
    for name in skill_names():
        for rel in skill_files(name):
            assert (tmp_path / ".agents/skills" / name / rel).is_file(), rel
    named = next(n for n in skill_names() if len(skill_files(n)) > 1)
    old = tmp_path / ".agents/skills" / named / "references/gone.md"
    old.write_text("old")
    written = sync_skill_files(tmp_path)
    assert not old.exists()
    assert f"removed .agents/skills/{named}/references/gone.md" in written
    assert not [s for s in stale_files(tmp_path) if s.startswith(".agents")]


def test_claude_md_imports_the_guide_and_keeps_its_own_text(tmp_path: Path):
    assert sync_claude(tmp_path) is not None
    assert (tmp_path / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert sync_claude(tmp_path) is None
    (tmp_path / "CLAUDE.md").write_text("# Mine\n")
    sync_claude(tmp_path)
    assert (tmp_path / "CLAUDE.md").read_text() == "@AGENTS.md\n\n# Mine\n"


def test_sync_replaces_only_the_marked_part(tmp_path: Path):
    guide = tmp_path / "AGENTS.md"
    guide.write_text(f"Read me first.\n\n{BEGIN}\nold kit\n{END}\n\n## This app\n\nkeep\n")
    sync_guide(tmp_path)
    text = guide.read_text()
    assert text.startswith(f"Read me first.\n\n{BEGIN}\n# Stario app guide")
    assert "old kit" not in text
    assert text.endswith(f"{END}\n\n## This app\n\nkeep\n")
    assert "AGENTS.md" not in stale_files(tmp_path)


def test_sync_moves_an_old_guide_to_the_marked_one(tmp_path: Path):
    guide = tmp_path / "AGENTS.md"
    guide.write_text("# Stario app guide\n\nold\n\n## This app\n\nkeep\n")
    sync_guide(tmp_path)
    text = guide.read_text()
    assert text.startswith(BEGIN)
    assert text.endswith("\n## This app\n\nkeep\n")


def test_sync_refreshes_the_generated_tests_of_an_app_that_uses_them(app: Path):
    page = app / "tests/_pagecheck.py"
    page.write_text("# edited\n")
    assert "tests/_pagecheck.py" in stale_files(app)
    assert sync_generated_tests(app) == [str(page)]
    assert page.read_text() == generated_text("tests/_pagecheck.py")
    (app / "tests/test_pages.py").write_text("# an old page check of its own\n")
    page.write_text("# edited\n")
    assert sync_generated_tests(app) == []


def test_new_prints_the_files_to_edit(tmp_path: Path):
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH")
    out = subprocess.run(
        [*CLI, "new", "app", "--db", "--no-verify", "--dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert out.returncode == 0, out.stderr
    for rel in ("app/main.py", "app/urls.py", "app/data.py", "app/layout.py", "app/pages/home.py"):
        assert f"==> {rel} <==" in out.stdout
    assert 'HOME = Route("GET /")' in out.stdout
    assert "uvx stario-create@latest check" in out.stdout
    assert (tmp_path / "app/CLAUDE.md").read_text() == "@AGENTS.md\n"


def test_cli_check_runs_every_step_and_names_the_failures(tmp_path: Path):
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH")
    out = subprocess.run(
        [*CLI, "new", "demo", "--no-verify", "--dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert out.returncode == 0, out.stderr
    root = tmp_path / "demo"
    ok = subprocess.run([*CLI, "check"], cwd=root, capture_output=True, text=True, timeout=300)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert ok.stdout.startswith("check: ok (")
    assert "passed" in ok.stdout
    (root / "app/state.py").write_text("x: int = 'a'\nSEEN = []\n")
    bad = subprocess.run([*CLI, "check"], cwd=root, capture_output=True, text=True, timeout=300)
    assert bad.returncode == 1
    assert "check: failed (pyrefly, pytest)" in bad.stdout
    assert "module-state" in bad.stdout
    req = subprocess.run(
        [*CLI, "request", "GET", "/"], cwd=root, capture_output=True, text=True, timeout=300
    )
    assert req.returncode == 0, req.stderr
    assert req.stdout.startswith("GET / -> 200 text/html")


@pytest.mark.parametrize("kit", ["auth", "auth-password", "tailwind", "browser", "pages"])
def test_kit_files_pass_ruff_in_the_app(tmp_path: Path, kit: str):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(tmp_path, "demo", db=True, agent_files=False)
    add_kit(tmp_path, kit)
    for argv in (["check", "--no-cache", "."], ["format", "--check", "--no-cache", "."]):
        out = subprocess.run(
            [sys.executable, "-m", "ruff", *argv], cwd=tmp_path, capture_output=True, text=True
        )
        assert out.returncode == 0, out.stdout + out.stderr
