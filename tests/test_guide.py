import ast
import re
import subprocess
import sys
import textwrap

import pytest

from stario_create.data import guide_text, skill_names, skill_text, template

PROFILES = ["app", "api"]


def _python_blocks(text: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", text, re.S)


@pytest.mark.parametrize("profile", PROFILES)
def test_guide_fits_rule_loader_budget(profile):
    # Rule loaders (Devin) cut always-on rules at 16 KB. The guide stays at the
    # skill size, so each app's `## This app` notes have room to grow.
    assert len(guide_text(profile).encode()) <= 9_000


@pytest.mark.parametrize("name", skill_names())
def test_skill_fits_inline(name):
    # Devin's skill tool shows a skill inline at 9.0 KB and returns only a
    # pointer at 15 KB; the agent then reads the file in parts.
    assert len(skill_text(name).encode()) <= 9_000


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
    assert "next SSE event" in guide_text()
    assert "timeout=2" in skill_text("stario-feature")


def test_guide_sets_a_budget_for_the_app_notes():
    assert "under 4 KB" in guide_text()


def test_guide_sends_only_what_a_person_must_see_to_a_browser():
    text = guide_text()
    assert "## Checks" in text
    assert "the user is the browser" in text
    assert "stario-browser-check" in text
    assert "No computer use." in text
    assert "Playwright" not in text
    assert "pyrefly checks each call" in text


def test_datastar_skill_lists_the_api_and_the_pro_only_attributes():
    text = skill_text("stario-api")
    for name in ["data.on(", "data.bind(", "data.indicator(", "at.get(", "sse.patch_elements("]:
        assert name in text
    assert "Datastar Pro only" in text
    assert "data.persist()" not in skill_text("stario-feature")
    assert "stario-api" in guide_text()


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
    text = skill_text("stario-api")
    for name in [
        "c.req.query",
        "ParsedQuery",
        "w.empty()",
        "relay.subscribe(",
        "security_headers()",
        "TestClient(",
    ]:
        assert name in text
    assert "stario-api" in guide_text()
    assert "stario-api" in skill_text("stario-feature")


def test_litewriter_skill_teaches_watch_with_a_sort():
    text = skill_text("stario-litewriter")
    assert "## The stream: `watch`" in text
    assert "`ORDER BY` and column names cannot be parameters" in text


def test_guide_routes_each_task_to_a_skill():
    text = guide_text()
    assert "## Which skill" in text
    assert "A static page (no command): no skill." in text
    for name in skill_names():
        assert f"`{name}`" in text.split("## Layout")[0]
