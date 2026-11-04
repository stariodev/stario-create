# `just` lists the targets. Install: uv tool install rust-just

set shell := ["bash", "-uo", "pipefail", "-c"]

# load secrets/config from .env (gitignored)
set dotenv-load := true

# run the app with hot reload
dev:
    # `python`, not `uv run python`: the app must be watchfiles' direct child.
    # A nested `uv run` wrapper swallows watchfiles' kill and leaves an orphan.
    uv run watchfiles 'python -m app.main' app/ static/

# run the app once, no reload
serve:
    uv run python -m app.main

# format, fix lint, typecheck, test - run before done; prints only problems
check:
    @uv run ruff format -q .
    @uv run ruff check -q --fix .
    @uv run pyrefly check 2>&1 | { grep -v ' INFO ' || true; }
    @uv run pytest -q --no-header

# the same checks without changes, for CI
ci:
    uv run ruff format --check .
    uv run ruff check .
    uv run pyrefly check
    uv run pytest -q

# run the tests
test *args:
    uv run pytest -q --no-header {{args}}

# refresh AGENTS.md, the skills, and the Cloud Agent files from the latest stario-create
sync:
    uvx stario-create@latest sync
