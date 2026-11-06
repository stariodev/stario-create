# stario-create

The project tool and agent guidance for building apps with [Stario](https://stario.dev). This repo tracks Stario 5. The framework itself lives at [stariodev/stario](https://github.com/stariodev/stario).

Two things ship from here:

- The `stario-create` CLI (`uvx stario-create`, or `uv tool install stario-create`). It scaffolds apps and keeps their guide and skills in sync.
- The files it installs: `AGENTS.md` (the always-on guide an app keeps at its root) and `skills/<name>/SKILL.md` (on-demand procedures an agent loads when the task matches).

## New app

```bash
uvx stario-create new my-app
cd my-app
just dev     # http://127.0.0.1:8000, reloads on change
just check   # lint, format, types, tests — run before done
```

`new` gives you a tested, runnable app:

- A uv project on Python 3.14 with `stario>=5.4,<6` and the dev tools.
- The feature-folder layout with one static `home` page.
- `static/js/datastar.js` vendored.
- `AGENTS.md` at the app root (Claude Code reads it directly).
- The skills installed into `.agents/skills/` and linked from `.claude/skills/`.
- A `justfile` (`dev`, `serve`, `check`, `fix`, `test`, `sync`). Without `just`, the recipes are plain commands — run them directly.
- `tests/test_pages.py`: the page check that replaces a browser for HTML.
- The app's own tests, run once so the scaffold starts green (`--no-verify` skips that).

`new` also writes a `.dockerignore`. It writes no `Dockerfile`: Yard detects a Stario app and writes the Containerfile itself (stario.dev/yard/what-runs). `new` takes `--dir` to pick the parent directory, `--force` to write into a non-empty one, and `--orjson` to add orjson and set it as the `stario.json` codec.

## Adding a kit

A kit is a set of tested files. Run it at the app root:

```bash
stario-create add            # list the kits
stario-create add auth       # sign-in with OpenID Connect (Google or any issuer), session, tests
stario-create add auth-password  # closed password accounts from the env, for an admin page
stario-create add tailwind   # Tailwind v4 and DaisyUI recipes, input.css, shell, theme switch
stario-create add browser    # scripts/browser.py, the rare Playwright check
stario-create add pages      # tests/test_pages.py, for an app from before 5.7
```

`add` writes each missing file. It replaces a file that still equals the scaffold version. It keeps a file that you changed and prints `merge by hand: <file>` with the path of the kit version. It appends the Tailwind recipes to the `justfile` once. `--no-deps` skips `uv add`.

## Syncing an app

In an app, `just sync` runs `uvx stario-create@latest sync`. Run this at the app root:

```bash
stario-create sync           # refresh AGENTS.md, skills, and missing Cloud Agent files
stario-create sync --check   # exit 1 when the guide, a skill, or a Cloud Agent file is stale
```

`sync` rewrites `AGENTS.md` to the bundled guide and keeps your `## This app` notes at the end. It overwrites each `.agents/skills/<name>/SKILL.md` and relinks `.claude/skills/<name>`. It writes `.cursor/environment.json` only when it is missing — a saved snapshot id survives — and always refreshes the tool-owned `.cursor/cloud-install.sh`. With `[tool.stario-create] profile = "api"` in the app's `pyproject.toml` it installs the short JSON API guide and removes the bundled skills. It prints one line per file changed, or "up to date".

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
| `stario-feature` | You add a live page in SQLite that every tab sees change, remove a page, or split a folder that grew. |
| `stario-view` | A page has a sort, a filter, paging, or a search as you type. |
| `stario-relay` | A live page keeps its state in memory, a command tells only its own tab something, or a page has an edit dialog. |
| `stario-jobs` | A command starts slow work: a job with queued, running, and done. |
| `stario-browser-check` | Before a browser: the test that answers each question about a page, and the two cases where a browser is right. |
| `stario-auth` | The app needs accounts: sign-in with OpenID Connect (`add auth`), closed password accounts (`add auth-password`), protected pages, rows that belong to one user. |
| `stario-api` | Any handler, view, or test code: every signature of `c`, `w`, `h.*`, Relay, Span, TestClient, `data.*`, `at.*`, `SSE`, and how a morph treats the page. |
| `stario-litewriter` | The app stores data in SQLite through `litewriter`: one writer thread, JSON tables with virtual columns, `watch` repaints a live page after a commit. |
| `stario-tailwind-daisyui` | The app is styled with Tailwind v4 and DaisyUI through the standalone binary. No Node. |
| `stario-client` | The page needs JavaScript: where it goes and how Python calls it. |

`npx skills add stariodev/stario-create` also works — it reads the `skills/` tree at this repo root.

## Served copies

`stario.dev` serves these files: `/AGENTS.md`, `/llms.txt`, `/llms-full.txt` (the guide and the skills in one file), `/skills/`, and `/skills/<name>/SKILL.md`.

## Repo layout

`AGENTS.md`, `llms.txt`, and `skills/` sit at the root. `npx skills`, `stario.dev`, and repo browsing all read them there. The wheel embeds copies under `stario_create/_data/` (hatchling `force-include`), so `uvx` works without a checkout. In a checkout the CLI reads the root files directly, so each file has one canonical copy.

## Changing the guide

The guide is checked against real code: `examples/chat-room` in the stario repo follows it. When a rule changes here, change the example there and run its tests. A snippet in `AGENTS.md` or a skill must run as written — the package tests parse every Python block, scaffold a project, and compile every generated file, and `stario-create new` runs the new app's tests. Before you change a pattern, build it in a scaffolded app and run `just check` there; then copy the passing code into the skill. Run the evals in `evals/` before and after a change to the guide.
