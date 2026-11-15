# stario-create

The project tool and agent guidance for building apps with [Stario](https://stario.dev). This repo tracks Stario 5. The framework itself lives at [stariodev/stario](https://github.com/stariodev/stario).

Two things ship from here:

- The `stario-create` CLI (`uvx stario-create`, or `uv tool install stario-create`). It scaffolds apps and keeps their guide and skills in sync.
- The files it installs: `AGENTS.md` (the always-on guide an app keeps at its root, enough for a first page), `CLAUDE.md` (one line, `@AGENTS.md`), and `skills/<name>/SKILL.md` with its `references/` (on-demand procedures an agent loads when the task matches).

## New app

```bash
uvx stario-create new my-app --db   # or `new .` for the current folder
cd my-app
just dev     # http://127.0.0.1:8000, reloads on change
just check   # format, lint, types, tests, the Stario lint; without just: uvx stario-create check
uvx stario-create request GET /    # a request through TestClient, no server
```

`new` gives you a tested, runnable app:

- A uv project on Python 3.14 with `stario>=5.8,<6` and the dev tools.
- One file per concern: `app/urls.py` (every route), `app/data.py` (the tables and SQL, with `--db`), `app/layout.py` (the document and shared markup), and `app/pages/home.py`, one static page.
- `static/js/datastar.js` vendored.
- `AGENTS.md` at the app root, and `CLAUDE.md` with `@AGENTS.md`, so Claude Code loads the guide next to a project's own notes.
- The skills installed into `.agents/skills/` and linked from `.claude/skills/`.
- A `justfile` (`dev`, `serve`, `check`, `fix`, `test`, `sync`). Without `just`, the recipes are plain commands — run them directly.
- `tests/test_pages.py`: the page check that replaces a browser for HTML, and the Stario lint. Its code is in the generated `tests/_pagecheck.py` and `tests/_lint.py`, which `sync` refreshes. The page check skips a page whose outside service (an API, a Node server) is down.
- The app's own tests, run once so the scaffold starts green (`--no-verify` skips that).

`new` also writes a `.dockerignore`. It writes no `Dockerfile`: Yard detects a Stario app and writes the Containerfile itself (stario.dev/yard/what-runs). The folder may be any path, `.` included; `app_name` comes from its name unless `--name` sets it. `--db` adds litewriter and opens the SQLite file in `bootstrap`. `--dir` picks the parent directory, `--force` writes into a non-empty folder, and `--orjson` adds orjson and sets it as the `stario.json` codec. Inside a repo whose `AGENTS.md` above the folder is already the Stario guide, `new` writes no second copy of the guide or the skills. It ends by printing what each file holds, and the full text of the files a new page changes, so an agent does not need to open them.

## Adding a kit

A kit is a set of tested files. Run it at the app root:

```bash
stario-create add            # list the kits
stario-create add auth       # sign-in with Google and GitHub; session; tests
stario-create add auth --password   # sign-up and sign-in with an email and a password
stario-create add tailwind   # Tailwind v4 and DaisyUI recipes, input.css, shell, theme switch
stario-create add browser    # scripts/browser.py, the rare Playwright check
stario-create add pages      # tests/test_pages.py and its generated files, for an older app
stario-create add page rooms room=/rooms/{room_id}   # page files, routes, register lines, links
```

`add` writes each missing file. It replaces a file that still equals the scaffold version. It keeps a file that you changed and prints `merge by hand: <file>` with the path of the kit version. It appends the Tailwind recipes to the `justfile` once. `--no-deps` skips `uv add`.

## Checking an app

Run these at the app root. Each prints only problems, and each problem states its fix.

```bash
stario-create check                 # ruff format, ruff --fix, pyrefly, pytest; every step runs
stario-create lint                  # the Stario rules alone (also part of the tests)
stario-create request GET /todos    # HTML, or the first SSE events of a stream
stario-create request POST /todos -j '{"title": "milk"}' GET /todos   # one client, in order
```

`request` runs in the app's own venv on a fresh data dir, reads `.env`, and starts no server. `-j` sends a Datastar action (JSON signals), `-s` sends signals on a GET, `-d k=v` a plain form field, `-H k:v` a header.

The lint rules: `attrs-after-children`, `time-unit` (`debounce=300` is 300 seconds), `module-state`, `env-outside-config`, `redirect-after-signals`, `datastar-import`, `json-module`, `bare-task`, `sleep-loop`, `pkill`. `# stario: ok` on a line skips it.

## Syncing an app

In an app, `just sync` runs `uvx stario-create@latest sync`. Run this at the app root:

```bash
stario-create sync           # refresh AGENTS.md, skills, and missing Cloud Agent files
stario-create sync --check   # exit 1 when the guide, a skill, or a Cloud Agent file is stale
```

`sync` replaces the part of `AGENTS.md` between `<!-- BEGIN stario-create -->` and `<!-- END stario-create -->` and keeps the rest (an older guide without the lines keeps its `## This app` notes). It adds `@AGENTS.md` to `CLAUDE.md`, overwrites each skill's `SKILL.md` and `references/` in `.agents/skills/<name>/`, relinks `.claude/skills/<name>`, and refreshes the generated `tests/_pagecheck.py` and `tests/_lint.py`. It writes `.cursor/environment.json` only when it is missing — a saved snapshot id survives — and always refreshes the tool-owned `.cursor/cloud-install.sh`. With `[tool.stario-create] profile = "api"` in the app's `pyproject.toml` it installs the short JSON API guide and removes the bundled skills. It prints one line per file changed, or "up to date".

## Without the CLI

To build an app by hand, the `pyproject.toml` needs these blocks:

```toml
[tool.ruff]
target-version = "py314"
line-length = 100
src = ["app", "tests"]
extend-exclude = [".agents", ".claude", ".cursor"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501", "B905"]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.pyrefly]
python-version = "3.14"
project-includes = ["app", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

Stario does not read `.env`. Configure with environment variables; `serve` reads `STARIO_*` through `ServerConfig.from_env()`. `STARIO_PORT` changes the port.

The guide and the skills are also at https://stario.dev/AGENTS.md and via `npx skills add stariodev/stario-create`.

## Skills

| Skill | Use it when |
| --- | --- |
| `stario-api` | Stario server names beyond AGENTS.md - an outside HTTP API with a cache and a test fake, cookies, uploads, static files, errors, TestClient options. Use when AGENTS.md lacks a server name or pyrefly rejects one. Not for h.*, data.*, at.*. |
| `stario-auth` | Accounts in a Stario app - password sign-up and sign-in (add auth --password), Google or GitHub sign-in (add auth), logout, protected pages, rows per user, API tokens. Use for any login, register, or permission need. |
| `stario-browser-check` | Load before a browser, a screenshot, Playwright, or computer use on a Stario app - the test that answers each question without a browser, and the two cases where a browser is right. |
| `stario-client` | JavaScript in a Stario app - where it goes and how Python calls it. Use before any script, addEventListener, long data.on expression, drag, picker, clipboard, or theme toggle. Not for what a GET or a data.* attribute does. |
| `stario-datastar` | Every Stario page-side option - h.* tags and helper types, data.* attributes and modifiers, at.* actions, SSE options, morph rules. Use when AGENTS.md lacks an h.*, data.* or at.* option. Not for server code. |
| `stario-feature` | Tests for a Stario page (stream, two tabs, bad input) and page extras - go to the page a command made, a navbar count, several tables, removing a page. Use when writing TestClient tests or one of these. Not for a first page. |
| `stario-jobs` | Slow work in a Stario app (a report, a model call, an import) as a job with live progress and clean shutdown, and a loop on a timer. Use when a command starts work that takes seconds, or work runs on a schedule. |
| `stario-litewriter` | Change a SQLite table that already holds rows - upgrade at start, a new column with its old rows filled, indexes, unique values, JSON columns, how watch wakes. Use when the schema of a filled database changes or a watch does not repaint. |
| `stario-relay` | A live Stario page on state in memory through Relay, a message to one tab, an edit dialog that keeps what the user typed. Use when state is not in SQLite. Not for SQLite pages (db.watch). |
| `stario-tailwind-daisyui` | Tailwind CSS v4 and DaisyUI for a Stario app (stario-create add tailwind, no Node), with a light and dark theme. Use when the app is styled with Tailwind or DaisyUI. |
| `stario-view` | Sort, filter, or page a Stario list through the URL query, and search as you type that patches one part. Use when a list gets sort links, filters, paging, or a search box. |

Each `SKILL.md` holds the common path in about 1k tokens; rare depth sits in `references/`, which the skill names.

`npx skills add stariodev/stario-create` also works — it reads the `skills/` tree at this repo root.

## Served copies

`stario.dev` serves these files: `/AGENTS.md`, `/llms.txt`, `/llms-full.txt` (the guide and the skills in one file), `/skills/`, and `/skills/<name>/SKILL.md`.

## Repo layout

`AGENTS.md`, `llms.txt`, and `skills/` sit at the root. `npx skills`, `stario.dev`, and repo browsing all read them there. The wheel embeds copies under `stario_create/_data/` (hatchling `force-include`), so `uvx` works without a checkout. In a checkout the CLI reads the root files directly, so each file has one canonical copy.

## Changing the guide

The guide is checked against real code: `examples/chat-room` in the stario repo follows it. When a rule changes here, change the example there and run its tests. A snippet in `AGENTS.md` or a skill must run as written: `tests/test_examples.py` builds a scaffolded app from each file's blocks (a block that starts with `# app/<file>.py` is that file; any other block runs inside a handler-shaped function) and runs pyrefly and the Stario lint on it. Size budgets hold the guide at 11.2 KB, the guide plus every skill description at 13.4 KB, each `SKILL.md` at 8 KB, and each reference at 6 KB. Before you change a pattern, build it in a scaffolded app and run `just check` there; then copy the passing code into the skill. Screen a change to the guide with stario-agent-bench before a release (`evals/` predates the 5.14 layout).
