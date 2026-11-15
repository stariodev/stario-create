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
    # first page, and leaves the `## This app` notes (4 KB) room under that cut. It
    # rides along on every agent step: 5.14.0 was 11.9 KB, this one may not grow.
    assert len(guide_text(profile).encode()) <= (11_200 if profile == "app" else 9_000)


def test_always_on_text_stays_small():
    # The guide and every skill description sit in context on every step. 5.14.0
    # had 13.9 KB (about 3.6k tokens); the kit stays at or below that.
    size = len(guide_text().encode()) + sum(len(description(n).encode()) for n in skill_names())
    assert size <= 13_400, size


@pytest.mark.parametrize("name", skill_names())
def test_skill_fits_inline(name):
    # A SKILL.md body holds the common path, about 1k tokens; depth goes in
    # references/. Devin shows a skill inline up to 9.0 KB.
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
    # What the skill covers, then "Use when/for/before" (or "Load before"): the words an
    # agent's task contains come first, so the skill loads when its topic comes up.
    text = description(name)
    assert any(f"Use {w}" in text for w in ("when", "for", "before")) or text.startswith(
        "Load before"
    ), text
    assert len(text) <= 260, len(text)


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


def test_guide_proves_a_live_update_from_the_stream():
    assert "timeout=2" in skill_text("stario-feature")
    assert "assert the next event" in skill_text("stario-feature")


def test_guide_sets_a_budget_for_the_app_notes():
    assert "under 4 KB" in guide_text()


def test_guide_sends_only_what_a_person_must_see_to_a_browser():
    text = guide_text()
    assert "`stario-browser-check`" in text
    browser = skill_text("stario-browser-check")
    assert "the user is the browser" in browser
    assert "computer use" in browser


def test_guide_names_the_tools_that_replace_rules():
    text = guide_text()
    for name in (
        "uvx stario-create@latest check",
        "uvx stario-create@latest request GET",
        "stario-create@latest add page",
        "kill $!",
        "pkill -f",
        "timeout",
        "acceptance suite",
        "Leave imports",
    ):
        assert name in text, name
    assert "Read both once" not in text


def test_datastar_skill_lists_the_api_and_the_pro_only_attributes():
    text = skill_text("stario-datastar")
    for name in ["data.on(", "data.bind(", "data.indicator(", "at.get(", "sse.patch_elements("]:
        assert name in text
    assert "Datastar Pro only" in text
    assert "data.persist()" not in skill_text("stario-feature")
    assert "stario-datastar" in guide_text()


def test_browser_check_owns_its_server():
    assert "stario-create@latest add browser" in skill_text("stario-browser-check")
    assert "playwright install chromium" in skill_text("stario-browser-check")
    script = template("kits/browser/scripts/browser.py").read_text()
    assert "async_playwright" in script
    assert 's.bind(("127.0.0.1", 0))' in script
    assert "server.terminate()" in script


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


def test_handler_skill_lists_the_server_api():
    text = kit_text()
    for name in [
        "c.req.query",
        "ParsedQuery",
        "w.empty()",
        "relay.subscribe(",
        "security_headers()",
        "TestClient(",
    ]:
        assert name in text, name
    assert "stario-api" in guide_text()
    assert "stario-api" in skill_text("stario-feature")


def test_litewriter_skill_teaches_watch_with_a_sort():
    text = skill_text("stario-litewriter")
    assert "## The stream: `watch`" in text
    assert "`ORDER BY` and column names cannot be parameters" in text


def test_guide_routes_each_task_to_a_skill():
    text = guide_text()
    assert "## Skills" in text
    for name in skill_names():
        assert f"`{name}`" in text


def test_api_skill_answers_what_agents_probed_for():
    # Agents read site-packages for these when the guide did not answer them
    # (stario-agent-bench, 2026-11). Each one is in the guide, a skill, or a reference.
    text = kit_text()
    for name in [
        "STARIO_PORT",
        "ServerConfig",
        "app.not_found(",
        "{path...}",
        "catch_errors(",
        "RedirectException(",
        "SignedCookie(",
        "read_form(",
        "Files(",
        "ASSETS.href(",
        "data={",
        'r.headers.get("location")',
        "db.watch(",
        "apsw.ConstraintError",
    ]:
        assert name in text, name


def test_guide_starts_an_app_in_one_command():
    text = guide_text()
    assert "uvx stario-create@latest new app --db" in text
    assert "Write every file in one message" in text


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
