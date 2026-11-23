import ast
import re
import subprocess
import sys
import textwrap

import pytest

from stario_create.data import guide_text, resource, skill_files, skill_names, skill_text, template
from stario_create.scaffold import BEGIN, END

PROFILES = ["app", "api"]


def kit_text() -> str:
    """The guide, every skill, and every reference: where a name must be found."""
    parts = [guide_text()]
    for name in skill_names():
        parts += [resource(f"skills/{name}/{rel}").read_text() for rel in skill_files(name)]
    return "\n".join(parts)


def description(name: str) -> str:
    head = skill_text(name).split("---")[1]
    return next(line for line in head.splitlines() if line.startswith("description: "))[13:]


def _python_blocks(text: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", text, re.S)


@pytest.mark.parametrize("profile", PROFILES)
def test_guide_fits_rule_loader_budget(profile):
    # Rule loaders (Devin) cut always-on rules at 16 KB. The app guide is enough for a
    # first app (pages, a live page, commands, accounts, search, paging) and leaves the
    # `## This app` notes (4 KB) room under that cut: 12 KB. It rides along on every step.
    assert len(guide_text(profile).encode()) <= (12_000 if profile == "app" else 9_000)


def test_always_on_text_stays_small():
    # The guide and every skill description sit in context on every step. draft 5.16 had
    # 14.3 KB with twelve skills; 5.13 has seven, so the total may not grow past that.
    size = len(guide_text().encode()) + sum(len(description(n).encode()) for n in skill_names())
    assert size <= 14_300, size


@pytest.mark.parametrize("name", skill_names())
def test_skill_fits_inline(name):
    # A SKILL.md body holds one task's path; Devin shows a skill inline up to 9.0 KB.
    # 5.13 has no references: each skill is one load, never a chain.
    assert len(skill_text(name).encode()) <= 8_000
    for rel in skill_files(name)[1:]:
        assert len(resource(f"skills/{name}/{rel}").read_text().encode()) <= 6_000, rel


@pytest.mark.parametrize("name", skill_names())
def test_each_reference_is_named_in_its_skill(name):
    # One level deep: the agent finds a reference only through its SKILL.md.
    for rel in skill_files(name)[1:]:
        assert f"`{rel}`" in skill_text(name), rel


@pytest.mark.parametrize("name", skill_names())
def test_description_says_when_to_use_the_skill(name):
    # What the skill covers (the words a task contains) first, then "Use when/for/before".
    # 300 characters, not 260 as in draft 5.16: seven skills replace twelve, so each description
    # names more triggers and its "Not for" case, and the sum is still smaller.
    text = description(name)
    assert any(f"Use {w}" in text for w in ("when", "for", "before")) or text.startswith(
        "Load before"
    ), text
    assert len(text) <= 300, len(text)


@pytest.mark.parametrize("name", skill_names())
def test_no_skill_sends_the_agent_to_another_skill(name):
    # A skill that points at a skill gets both loaded (draft 5.15: stario-auth pulled in
    # stario-litewriter in 6/6 runs). Only the guide routes; a skill may name one other
    # skill for a case it does not cover, at most once.
    text = skill_text(name).split("---", 2)[2]
    others = [n for n in skill_names() if n != name and f"`{n}`" in text]
    assert len(others) <= 1, others


def test_guide_marks_the_kit_part_for_sync():
    text = guide_text()
    assert text.startswith(BEGIN + "\n# Stario app guide")
    assert text.index(END) < text.index("\n## This app")


@pytest.mark.parametrize("profile", PROFILES)
def test_guide_python_blocks_parse(profile):
    blocks = _python_blocks(guide_text(profile))
    assert profile == "api" or blocks
    for block in blocks:
        ast.parse(block)


@pytest.mark.parametrize("name", skill_names())
def test_skill_python_blocks_parse(name):
    for block in _python_blocks(skill_text(name)):
        ast.parse(textwrap.dedent(block))


@pytest.mark.parametrize("profile", PROFILES)
def test_guide_python_blocks_are_formatted(tmp_path, profile):
    copy = tmp_path / "AGENTS.md"
    copy.write_text(guide_text(profile))
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--preview",
            "--line-length",
            "100",
            str(copy),
        ],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("profile", PROFILES)
def test_guide_ends_with_this_app_section(profile):
    assert guide_text(profile).rstrip().rsplit("## ", 1)[-1].startswith("This app")


def test_guide_sets_a_budget_for_the_app_notes():
    assert "under 4 KB" in guide_text()


def test_guide_is_the_loop_and_names_the_tools_that_replace_rules():
    text = guide_text()
    for name in (
        "uvx stario-create@latest new app --db",
        "add auth --password",
        "uvx stario-create@latest check",
        "uvx stario-create@latest request GET",
        "lsof -ti",
        "pkill -f",
        "timeout",
        "acceptance suite",
        "foreground",
        "`check` sorts and drops them",
    ):
        assert name in text, name
    assert "Read both once" not in text


def test_guide_states_the_facts_that_cost_runs():
    # stario-agent-bench notes/kit-learnings.md, "Facts the kit must get right": each one
    # is in the always-on guide, or a tool makes it unnecessary (see DESIGN.md).
    text = " ".join(guide_text().split())
    for fact in (
        "`@baked`",  # page() runs once with placeholders
        "per-request part",  # a signed-in header is a parameter
        "Files(ASSETS.directory",  # a file that keeps its name
        "replaces only files still equal to the scaffold",  # kits right after new
        "w.redirect(url, 303)",
        "SSE(w).navigate(url)",
        '"300ms"',
        "raises `QueryError`",  # db.value on no row
        "a row or None",  # db.one
        "apsw.ConstraintError",
        "to_thread",  # hash before the write
        "yields only when its result changes",  # watch
        "chain steps",  # request starts on an empty database
        "`classes(...)`",
        "before the children",
        "cast(list[str], loads(s))",
        "list[HtmlElement]",
        "second `GET /` raises",
        "tests/test_pages.py",
        "STARIO_PORT",
        "DATABASE_PATH",
        "lsof -ti tcp:8000",  # kill $! does not reach an earlier call's job
        "keep the route names",  # the login kit's tests survive a rewrite
        "[*tags]",  # a list[str] variable in data.signals is refused (3 of 4 conduit runs, dev1 draft)
        "no server call",  # tags being typed stay in the tab (both dev1-draft Haiku runs raced)
        "STARIO_HOST=0.0.0.0",  # a host's PORT needs every interface
    ):
        assert fact in text, fact


def test_browser_check_owns_its_server():
    text = skill_text("stario-js")
    assert "stario-create@latest add browser" in text
    assert "playwright install chromium" in text
    script = template("kits/browser/scripts/browser.py").read_text()
    assert "async_playwright" in script
    assert 's.bind(("127.0.0.1", 0))' in script
    assert "server.terminate()" in script


def test_tests_skill_proves_a_live_update_from_the_stream():
    text = skill_text("stario-tests")
    assert "timeout=2" in text
    assert "assert the next event" in text


def test_reference_lists_the_pro_only_attributes():
    text = skill_text("stario-reference")
    assert "Datastar Pro only" in text
    for name in ("persist", "query_string", "data.on_intersect(", 'data.preserve_attr("open")'):
        assert name in text, name


@pytest.mark.parametrize("name", skill_names())
def test_indicator_sits_on_the_sending_element(name):
    """data.indicator belongs on the element whose data.on sends the request.

    A submit fetch belongs to the <form>, so a Button inside it must not
    carry the indicator (5.3.3 put it on the button; it never fires).
    """
    for block in _python_blocks(skill_text(name)):
        src = textwrap.dedent(block)
        tree = ast.parse(src)
        for form in ast.walk(tree):
            if not (
                isinstance(form, ast.Call)
                and isinstance(form.func, ast.Attribute)
                and form.func.attr == "Form"
            ):
                continue
            if 'data.on("submit"' not in (ast.get_source_segment(src, form) or ""):
                continue
            for node in ast.walk(form):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Button"
                    and "data.indicator(" in (ast.get_source_segment(src, node) or "")
                ):
                    pytest.fail("data.indicator on h.Button inside a submitting h.Form")


def test_guide_routes_each_task_to_a_skill():
    text = guide_text()
    assert "## Skills" in text
    for name in skill_names():
        assert f"`{name}`" in text


def test_kit_answers_what_agents_probed_for():
    # Agents read site-packages for these when the guide did not answer them
    # (stario-agent-bench, 2026-11). Each one is in the guide or a skill.
    text = kit_text()
    for name in [
        "c.req.query",
        "w.empty()",
        "relay.subscribe(",
        "security_headers(",
        "TestClient(",
        "STARIO_PORT",
        "app.not_found(",
        "{path...}",
        "catch_errors(",
        "RedirectException(",
        "SignedCookie(",
        "read_form(",
        "Files(",
        "ASSETS.href(",
        "data=",
        'r.headers.get("location")',
        "db.watch(",
        "apsw.ConstraintError",
        "getlist(",
        "Every HTML tag is `h.<Name>`",
        "execute_script(",
        "w.respond(",
    ]:
        assert name in text, name


@pytest.mark.parametrize("name", skill_names())
def test_skill_frontmatter_is_plain_yaml(name):
    # A ": " or " #" in a plain YAML scalar breaks the frontmatter: `npx skills add`
    # skips the skill and Claude Code does not list it.
    head = skill_text(name).split("---")[1]
    for line in head.strip().splitlines():
        key, _, value = line.partition(": ")
        assert key in ("name", "description"), line
        assert ": " not in value, line
        assert " #" not in value, line
        assert not value.startswith(("'", '"', "[", "{")), line
