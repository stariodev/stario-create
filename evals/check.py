"""check.py RUN_DIR TASK -> JSON rubric. Static checks plus `just check`. Heuristic; diffs get a human read too."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

run = Path(sys.argv[1])
task = sys.argv[2]
app = run / "app"
NAME = {
    "T1-todos": "todos",
    "T2-reports": "reports",
    "T3-notes": "notes",
    "T4-about": "about",
    "T5-rooms": "rooms",
    "T6-search": "search",
    "T7-stats": "stats",
    "T8-sort": "todos",
    "T9-author": "todos",
    "T10-bug": "todos",
    "T11-auth": "todos",
    "T12-style": "todos",
}[task]
res: dict = {"task": task}


def src(p: Path) -> str:
    try:
        return p.read_text()
    except OSError, UnicodeDecodeError:
        return ""


def all_py() -> dict[str, str]:
    return {
        str(p.relative_to(run)): src(p) for p in app.rglob("*.py") if "__pycache__" not in p.parts
    }


files = all_py()
code = "\n".join(files.values())

# 1. just check, step by step
steps = {}
for name, cmd in [
    ("ruff", "uv run ruff check ."),
    ("format", "uv run ruff format --check ."),
    ("pyrefly", "uv run pyrefly check"),
    ("pytest", "uv run pytest -q"),
]:
    p = subprocess.run(cmd, shell=True, cwd=run, capture_output=True, text=True, timeout=600)
    steps[name] = p.returncode == 0
    if name == "pytest":
        m = re.search(r"(\d+) passed", p.stdout)
        res["tests_passed"] = int(m.group(1)) if m else 0
res["check"] = steps
res["check_all"] = all(steps.values())
res["git_changed"] = subprocess.run(
    ["git", "diff", "--name-only", "HEAD"], cwd=run, capture_output=True, text=True
).stdout.split()

# 2. structure
new_dirs = sorted(
    d.name
    for d in (app / "features").iterdir()
    if d.is_dir() and d.name not in {"home", "__pycache__"}
)
res["feature_dirs"] = new_dirs
fdir = app / "features" / NAME
if not fdir.is_dir() and new_dirs:
    fdir = app / "features" / new_dirs[0]
res["feature_files"] = sorted(p.name for p in fdir.glob("*.py")) if fdir.is_dir() else []
res["has_core_files"] = all(
    (fdir / f).is_file() for f in ("__init__.py", "urls.py", "views.py", "handlers.py")
)
res["registered_in_main"] = bool(
    re.search(r"\.register\(app\)|register_\w+\(", src(app / "main.py"))
) and fdir.name in src(app / "main.py")
res["test_file"] = sorted(
    p.name for p in (run / "tests").glob("test_*.py") if p.name != "test_home.py"
)
res["files_outside_features"] = sorted(
    f
    for f in files
    if not f.startswith("app/features/")
    and f
    not in {
        "app/__init__.py",
        "app/main.py",
        "app/config.py",
        "app/assets.py",
        "app/common/__init__.py",
        "app/common/shell.py",
    }
    and src(run / f)
    != subprocess.run(["git", "show", f"HEAD:{f}"], cwd=run, capture_output=True, text=True).stdout
)
res["home_links"] = NAME in src(app / "features/home/views.py") or f"/{NAME}" in src(
    app / "features/home/views.py"
)

# 3. route methods from urls.py
routes: dict[str, str] = {}
for m in re.finditer(
    r"^(\w+)\s*=\s*Route\(\s*\"(GET|POST|PUT|PATCH|DELETE)[ \"]", src(fdir / "urls.py"), re.M
):
    routes[m.group(1)] = m.group(2)
res["routes"] = routes
res["has_live_route"] = bool(
    re.search(r"Route\(\s*\"GET[^\"]*/(live|subscribe|stream|events)", src(fdir / "urls.py"))
)

# 4. commands that render: POST factories that write HTML or patch elements
hsrc = src(fdir / "handlers.py")
bad_commands = []
private_posts = []
try:
    tree = ast.parse(hsrc)
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    defs += [
        m
        for c in tree.body
        if isinstance(c, ast.ClassDef)
        for m in c.body
        if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    factories = {n.name: ast.get_source_segment(hsrc, n) or "" for n in defs}
    for call in re.finditer(r"app\.add\(\s*(\w+)\s*,\s*(?:self\.)?(\w+)\b", hsrc):
        route, fac = call.group(1), call.group(2)
        if routes.get(route, "GET") != "GET":
            body = factories.get(fac, "")
            renders = bool(re.search(r"\bw\.html\(|patch_elements\(", body))
            mutates = bool(re.search(r"publish\(|\.write\(|\.push\(|create_task\(", body))
            if "w.redirect(" in body or (renders and mutates):
                bad_commands.append(fac)
            elif renders:
                private_posts.append(fac)
            if re.search(r"await asyncio\.sleep\(", body) and "create_task" not in body:
                bad_commands.append(fac + ":sleeps_inline")
except SyntaxError:
    bad_commands.append("handlers.py:syntax")
res["commands_that_render"] = bad_commands
res["private_posts"] = private_posts

# 5. Datastar usage
vsrc = "\n".join(src(p) for p in fdir.glob("*.py"))
res["init_live_retry_always"] = bool(re.search(r"data\.init\(\s*at\.get\(.*retry=\"always\"", vsrc))
res["c_alive"] = "c.alive(" in vsrc
res["signals_if_missing"] = "if_missing=True" in vsrc
res["preserve_open"] = bool(re.search(r"preserve_attr\(\s*\[?\s*\"open\"", vsrc))
res["server_renders_open"] = bool(re.search(r"[\"']open[\"']\s*:\s*True", vsrc))
res["showModal"] = "showModal" in vsrc
res["indicator"] = bool(re.search(r"data\.indicator\(|classList\.add\(|aria-busy", vsrc))
res["create_task"] = bool(re.search(r"\b(c\.)?app\.create_task\(", vsrc))
res["bare_asyncio_create_task"] = "asyncio.create_task(" in code
_store_src = vsrc + src(app / "main.py")
res["store"] = (
    "litewriter"
    if "litewriter" in _store_src.lower()
    else "sqlite3"
    if "sqlite3" in _store_src
    else "memory"
)
res["relay"] = "Relay" in vsrc
res["watch"] = ".watch(" in vsrc

# 6. forbidden patterns
res["json_dumps"] = "json.dumps" in code
res["url_for"] = "url_for" in code
res["form_method_post"] = bool(re.search(r"[\"']method[\"']\s*:\s*[\"']post", code, re.I))
res["environ_outside_config"] = sorted(
    f for f, s in files.items() if "os.environ" in s and f != "app/config.py"
)
res["new_js_files"] = sorted(
    str(p.relative_to(run)) for p in (run / "static").rglob("*.js") if p.name != "datastar.js"
)
_app_js = {
    str(p.relative_to(run)): src(p)
    for p in (run / "static").rglob("*.js")
    if p.name != "datastar.js"
}
res["js_in_python"] = sorted(
    f
    for f, s in files.items()
    if re.search(r"addEventListener\(|getElementById\(|window\.\w+\s*=[^=]|=>\s*\{", s)
)
res["inline_script"] = sorted(
    f for f, s in files.items() if re.search(r"h\.Script\(\s*SafeString", s)
)
res["js_global_listeners"] = sorted(
    f for f, s in _app_js.items() if re.search(r"\b(window|document)\.addEventListener\(", s)
)
res["js_builds_html"] = sorted(
    f
    for f, s in _app_js.items()
    if re.search(r"createElement\(|\.innerHTML\s*=|insertAdjacentHTML", s)
)
res["module_mutable_state"] = sorted(
    f
    for f, s in files.items()
    if f.startswith("app/features/")
    and re.search(r"^[A-Za-z_]\w*\s*(:\s*[^=]+)?=\s*(\[\]|\{\}|dict\(|list\(|defaultdict)", s, re.M)
)
allf = "\n".join(s for f, s in files.items() if f.startswith("app/features/"))
res["navigate"] = "navigate(" in allf
res["redirect_in_features"] = "w.redirect(" in allf
res["get_patch_handlers"] = len(re.findall(r"patch_elements\(", allf))
res["non_feature_pkgs"] = sorted(
    d.name
    for d in app.iterdir()
    if d.is_dir() and d.name not in {"features", "common", "__pycache__"}
)
res["env_version_in_config"] = "APP_VERSION" in src(app / "config.py")


def wrapper_factories(text: str) -> list[str]:
    """Factories that take nothing and only return an inner handler: redundant, not wrong."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef) or n.args.args or n.args.kwonlyargs:
            continue
        inner = [b for b in n.body if isinstance(b, ast.AsyncFunctionDef)]
        last = n.body[-1] if n.body else None
        if inner and isinstance(last, ast.Return) and isinstance(last.value, ast.Name):
            found.append(n.name)
    return found


res["wrapper_factories"] = sorted(
    f"{Path(f).parent.name}/{name}"
    for f, s in files.items()
    if f.startswith("app/")
    for name in wrapper_factories(s)
)


def handler_factories(text: str) -> list[str]:
    """Module-level functions that return an inner async handler. The guide uses page classes."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return [
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and any(isinstance(b, ast.AsyncFunctionDef) for b in n.body)
        and isinstance(n.body[-1], ast.Return)
    ]


res["handler_factories"] = sorted(
    f"{Path(f).parent.name}/{name}"
    for f, s in files.items()
    if f.startswith("app/features/") and f.endswith("handlers.py")
    for name in handler_factories(s)
)
res["page_class"] = bool(re.search(r"^class \w+Page\b", hsrc, re.M)) and "def register(" in hsrc
res["layer_classes"] = sorted(
    m.group(1)
    for m in re.finditer(
        r"^class (\w+(?:Service|Repository|Repo|Manager|Command|Result|Editor|Controller))\b",
        code,
        re.M,
    )
)
res["view_from_query"] = "c.req.query" in vsrc or "from_query(" in vsrc
res["tab_channel"] = bool(re.search(r"publish\(\s*f[\"']tab\.", vsrc))
res["reply_before_execute"] = not re.search(
    r"await self\.db\.write\([^\n]*\n(?:[^\n]*\n){0,2}\s*w\.empty\(\)", hsrc
)

# 6b. task probes
repo = {
    str(p.relative_to(run)): src(p)
    for p in run.rglob("*")
    if p.is_file()
    and p.suffix in {".py", ".css", ".toml", ".md", ".sh", ""}
    and not {".venv", ".git", "__pycache__", "node_modules"} & set(p.parts)
    and p.stat().st_size < 500_000
}
if task == "T11-auth":
    tsrc = src(fdir / "data.py") + src(fdir / "handlers.py")
    res["auth"] = {
        "hash": bool(re.search(r"scrypt|pbkdf2|argon2|bcrypt", code)),
        "hmac_cookie": "hmac" in code and "set_cookie" in code,
        "httponly": "httponly=True" in code,
        "secret_in_config": bool(re.search(r"secret", src(app / "config.py"), re.I)),
        "user_from_signal": bool(
            re.search(r"signals(\.get\(|\[)\s*[\"'](user|user_id|owner|owner_id)[\"']", code)
        ),
        "logout_post": bool(re.search(r"Route\(\s*\"POST [^\"]*(logout|sign-?out)", code)),
        "logout_get": bool(re.search(r"Route\(\s*\"GET [^\"]*(logout|sign-?out)", code)),
        "require_mw": bool(re.search(r"require\(|middleware=\[|app\.use\(", code)),
        "todos_per_user": bool(re.search(r"user_id|owner", tsrc)),
        "state_user": "c.state" in tsrc,
        "tests_redirect": bool(
            re.search(
                r"303|follow_redirects", "\n".join(src(p) for p in (run / "tests").glob("*.py"))
            )
        ),
    }
if task == "T12-style":
    css_in = src(run / "frontend/src/input.css")
    out = run / "static/css/output.css"
    raw_colors = re.findall(r"\b(?:bg|text|border)-(?:gray|slate|zinc|neutral|white|black)\b", code)
    res["style"] = {
        "node": (run / "package.json").exists()
        or (run / "node_modules").exists()
        or bool(re.search(r"\bnpx?\b", src(run / "justfile"))),
        "unpinned_latest": sorted(
            f for f, s in repo.items() if "releases/latest" in s and not f.startswith(".eval")
        ),
        "input_css_daisyui": "daisyui" in css_in,
        "source_py": bool(re.search(r"@source\s+\"[^\"]*\.py\"", css_in)),
        "output_built": out.is_file() and out.stat().st_size > 2000 and "btn" in src(out),
        "stylesheet_linked": "output.css" in src(app / "assets.py"),
        "just_css": bool(re.search(r"^css:", src(run / "justfile"), re.M)),
        "binary_ignored": "tailwindcss" in src(run / ".gitignore"),
        "theme_attr": "data-theme" in code,
        "theme_survives_morph": bool(
            re.search(r"preserve_attr\(\s*\[?\s*\"data-theme\"|ignore_morph\(", code)
        ),
        "theme_signal": bool(re.search(r"[\"']_?theme[\"']|\$_?theme", code)),
        "theme_server_route": bool(re.search(r"Route\(\s*\"(POST|PUT) [^\"]*theme", code)),
        "raw_colors": len(raw_colors),
    }

# 7. size
d = subprocess.run(
    ["git", "diff", "--shortstat", "HEAD"], cwd=run, capture_output=True, text=True
).stdout
u = subprocess.run(["git", "status", "--porcelain"], cwd=run, capture_output=True, text=True).stdout
res["diff"] = d.strip()
res["untracked"] = [
    line[3:]
    for line in u.splitlines()
    if line.startswith("??") and not line[3:].startswith(".eval")
]
try:
    res["seconds"] = int(src(run / ".eval-seconds").strip())
except ValueError:
    res["seconds"] = None
try:
    _fm = json.loads(src(run / ".eval-transcript.md")).get("final_metrics") or {}
    res["ktok"] = round(
        (_fm.get("total_prompt_tokens", 0) - _fm.get("total_cached_tokens", 0)) / 1000
    )
    res["ktok_total"] = round(_fm.get("total_prompt_tokens", 0) / 1000)
    res["steps"] = _fm.get("total_steps")
except Exception:
    pass
print(json.dumps(res, indent=1))
