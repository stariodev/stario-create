from pathlib import Path

import pytest

from stario_create.kits import KITS, add_kit, kit_files
from stario_create.scaffold import ScaffoldError, scaffold_files


@pytest.fixture
def app(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    scaffold_files(tmp_path, "demo")
    return tmp_path


@pytest.mark.parametrize("name", sorted(KITS))
def test_a_kit_writes_its_files_into_a_new_app(app: Path, name: str):
    added = add_kit(app, name)
    assert added.merge == []
    for rel, _ in kit_files(name):
        assert (app / rel).is_file(), rel
    for py in app.rglob("*.py"):
        compile(py.read_text(), str(py), "exec")
    assert add_kit(app, name).written == []


def test_auth_fills_the_app_name_and_replaces_untouched_files(app: Path):
    add_kit(app, "auth")
    config = (app / "app/config.py").read_text()
    assert '"demo"' in config
    assert "SESSION_SECRET" in config
    assert "LOGIN_CLIENT_ID" in config
    assert "Issuer(" in (app / "app/main.py").read_text()
    assert "FakeIssuer" in (app / "tests/conftest.py").read_text()
    assert not (app / "app/features/signup").exists()


def test_auth_password_has_no_sign_up_and_a_hash_recipe(app: Path):
    add_kit(app, "auth-password")
    assert "LOGIN_ACCOUNTS" in (app / "app/config.py").read_text()
    assert "\npassword-hash email:" in (app / "justfile").read_text()
    assert not (app / "app/features/signup").exists()


def test_a_changed_file_is_left_for_a_merge(app: Path):
    main = app / "app/main.py"
    main.write_text(main.read_text() + "# mine\n")
    added = add_kit(app, "auth")
    assert [rel for rel, _ in added.merge] == ["app/main.py"]
    assert main.read_text().endswith("# mine\n")


def test_tailwind_appends_its_recipes_once(app: Path):
    add_kit(app, "tailwind")
    add_kit(app, "tailwind")
    justfile = (app / "justfile").read_text()
    assert justfile.count("\ntailwind:") == 1
    assert "\ncheck:" in justfile
    assert "css/output.css" in (app / "app/assets.py").read_text()
    assert "tailwindcss" in (app / ".gitignore").read_text().splitlines()


def test_a_built_stylesheet_is_never_replaced(app: Path):
    css = app / "static/css/output.css"
    css.parent.mkdir(parents=True, exist_ok=True)
    css.write_text("built")
    assert add_kit(app, "tailwind").merge == []
    assert css.read_text() == "built"


def test_an_unknown_kit_names_the_kits(app: Path):
    with pytest.raises(ScaffoldError) as err:
        add_kit(app, "nope")
    assert "auth" in err.value.hint


def test_a_new_app_has_the_page_check(app: Path):
    assert (app / "tests/test_pages.py").is_file()
