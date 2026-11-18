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
stario-create add auth --password   # sign-up and sign-in with an email and a password (plain forms)
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

The lint rules: `attrs-after-children`, `classes-in-dict`, `time-unit` (`debounce=300` is 300 seconds), `redirect-status` (`w.redirect(url)` answers 307, which repeats a POST), `redirect-after-signals`, `order-by-param`, `module-state`, `env-outside-config`, `datastar-import`, `json-module`, `bare-task`, `sleep-loop`, `pkill`. `# stario: ok` on a line skips it.

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
| `stario-accounts` | Accounts past the add auth kits in a Stario app - Google or GitHub sign-in setup, a signed-in header, rows each user owns, profiles and settings, password change, roles and admin pages, API tokens. Use when the task goes past sign-up, sign-in and protected pages (AGENTS.md has those). |
| `stario-background` | State and work outside SQLite in a Stario app - a live page on state in memory (Relay), slow work with live progress (an export, an import, a model call), a timer loop, a message to one tab, clean shutdown. Use when state is not in the database or work outlasts the request. |
| `stario-js` | JavaScript in a Stario app - a static/js file per behaviour, app.name functions called from data.on, clipboard, drag, charts, editors, keyboard input; the browser check for JS that holds state. Use before writing any script or addEventListener. Not for what data.* attributes already do. |
| `stario-migrate` | Change SQLite tables that already hold rows in a Stario app - add a column and fill old rows, rename or retype one, an index, a test on an old database. Use when a table with rows gets a new or changed column (an app in use, an upgrade). Not for new tables, which CREATE TABLE IF NOT EXISTS makes. |
| `stario-outside-api` | Call an outside HTTP API from a Stario app - an httpx client opened in bootstrap, typed results, a cache, a 404 or 502 page when the service fails, offline tests with httpx.MockTransport. Use when pages read data from another service over HTTP. |
| `stario-reference` | Stario, Datastar and litewriter names past AGENTS.md - more data.* and at.* options, SSE morph modes, dialogs, infinite scroll, a live navbar count, uploads, signed cookies, middleware, error pages, server settings, JSON endpoints. Use when AGENTS.md lacks a name or pyrefly rejects one. |
| `stario-tests` | TestClient tests for a Stario app - pages, Datastar commands, plain forms, live streams in two tabs, sign-in, bad input. Use when the task asks for tests or ships no acceptance suite. Not when the task ships its own suite (npm test, Playwright). |

Each skill is one `SKILL.md` that holds one task's path, so a task loads one skill or none. The
guide routes to them; no skill sends the agent on to another. `stario-tailwind-daisyui`,
`stario-browser-check`, `stario-view`, `stario-feature`, `stario-datastar`, `stario-api`,
`stario-relay` and `stario-jobs` of 5.x are gone: their common parts are in `AGENTS.md`, the
rest in the seven skills above, and `sync` removes the old folders.

`npx skills add stariodev/stario-create` also works — it reads the `skills/` tree at this repo root.

## Served copies

`stario.dev` serves these files: `/AGENTS.md`, `/llms.txt`, `/llms-full.txt` (the guide and the skills in one file), `/skills/`, and `/skills/<name>/SKILL.md`.

## Repo layout

`AGENTS.md`, `llms.txt`, and `skills/` sit at the root. `npx skills`, `stario.dev`, and repo browsing all read them there. The wheel embeds copies under `stario_create/_data/` (hatchling `force-include`), so `uvx` works without a checkout. In a checkout the CLI reads the root files directly, so each file has one canonical copy.

## Changing the guide

The guide is checked against real code: `examples/chat-room` in the stario repo follows it. When a rule changes here, change the example there and run its tests. A snippet in `AGENTS.md` or a skill must run as written: `tests/test_examples.py` builds a scaffolded app from each file's blocks (a block that starts with `# app/<file>.py` is that file; any other block runs inside a handler-shaped function) and runs pyrefly and the Stario lint on it. Size budgets hold the guide at 12 KB (so 4 KB of app notes fit under the 16 KB rule-loader cut), the guide plus every skill description at 14.3 KB, each description at 300 characters, and each `SKILL.md` at 8 KB. `DESIGN.md` says what is always on, what is in a skill, and why. Before you change a pattern, build it in a scaffolded app and run `just check` there; then copy the passing code into the skill. Screen a change with the probes in `evals/` (routing on Haiku and Sonnet, decisions on Opus, a few cents a case), then with stario-agent-bench before a release.
