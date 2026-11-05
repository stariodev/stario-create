# Changelog

All notable changes to stario-create are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed

- The guide says that `same_origin()` is the CSRF guard, so an app adds no
  CSRF tokens, and that it does not check GET, so a GET never changes
  state. The API profile has no forms and does not change.

## 5.10.0

### Changed

- The guide is 6.4 KB, down from 9.0 KB. Its last section is no longer named
  in the intro, so a search for `## This app` finds the section and not the
  whole file. It adds two rules: change a file with the Edit tool and run
  Python as `uv run python`, and start a bug fix with a test that fails.
- `stario-api` is a lookup. The guide and the recipe skills no longer tell
  the agent to load it for every signature; pyrefly checks each call.
- `just check` formats and fixes lint first, then prints only problems.
  `just ci` runs the same checks without changes. `just test` takes pytest
  arguments.
- New apps have no `.python-version`. `requires-python` pins 3.14 for uv,
  and a pyenv shim no longer breaks a bare `python3`.
- `Config` has one field with a default per setting; `from_env` reads each
  field from the env var of the same name. The home page links to each page
  in `LINKS`, and `main.py` marks the register lines with `# pages`.
- `tests/test_pages.py` finds each page from the `GET` routes in each
  `urls.py`, so it needs no `EXTRA` list.
- New apps ignore E501 (ruff format owns the line length) and set the
  pytest-asyncio fixture loop scope, so a test run prints no warning.

## 5.9.3

### Changed

- New apps need stario 5.3.3. Its `server.shutdown` span names each
  cancelled task, which the test in `stario-jobs` checks, and its
  `c.alive()` and `app.shutdown` leave no callback behind.
- The API profile guide reads `app.shutdown` once per timer loop, like the
  `stario-jobs` skill. `stario-api` says the same.

## 5.9.2

### Changed

- The timer loop in `stario-jobs` reads `app.shutdown` once, before the
  loop. Each read makes a new shield, and a pending shield keeps a callback
  on the app's future, so one read per pass grows without bound.
- A loop that waits on an event waits on `shutdown` too, and clears the
  event after the wait.

## 5.9.1

### Changed

- A timer loop ends each pass with `await asyncio.wait({app.shutdown},
  timeout=interval)`, never `asyncio.sleep`. The loop then stops at once
  when shutdown starts. The guide has the rule, the `stario-jobs` skill has
  the pattern and a test, and `stario-api` lists `app.shutdown`.
- `stario-jobs` shows the `server.shutdown.task_cancelled` event from
  stario 5.3.2: give each loop a `name`, and a test checks that no loop is
  cancelled.

## 5.9.0

### Changed

- New apps check types with pyrefly instead of pyright. The justfile runs
  `uv run pyrefly check`, the dev dependencies list `pyrefly`, and
  `pyproject.toml` gets a `[tool.pyrefly]` table. pyrefly passes more of
  the typing conformance suite than pyright and runs in under a second.
- The guide and the skills say pyrefly.
- `sync --check` flags a justfile whose `check` recipe still runs pyright.

## 5.8.0

### Changed

- The guide is 8.9 KB, down from 12 KB, so each app has about 3 KB more
  room under the 16 KB rule limit. The test example, the common-mistakes
  table, and rules that a skill already holds moved out. The rules for
  every task stay.
- The guide sets a budget for `## This app`: under 4 KB. A deep note on one
  topic goes in its own file, with a line that says when to read it.

### Added

- `sync` and `sync --check` print a warning when `## This app` is larger
  than 4,000 bytes. The warning does not change the exit code.

## 5.7.0

### Added

- `stario-create add <kit>` writes tested files into an app. It writes a
  missing file, replaces a file that still equals the scaffold version,
  and prints `merge by hand` for a file that the app changed.
  - `auth`: `app/common/session.py`, the login and sign-up pages, the
    users table, the `Config` fields, the wiring in `main.py`, and the
    tests. It adds `litewriter`.
  - `tailwind`: the `justfile` recipes (the binary and DaisyUI, pinned),
    `input.css`, the shell with the theme restore, and `theme.js`.
  - `browser`: `scripts/browser.py`. It starts the app on a free port with
    the settings in `.env`, waits for the port, prints console errors, and
    saves a screenshot.
  - `pages`: the page check, for an app from before 5.7.
- `stario-create new` writes `tests/test_pages.py`. It opens `/`, follows
  every local link, and fails on an action with no route, an undefined
  `$signal`, a stream that changes its element, a `<dialog>` that closes on
  a repaint, and a duplicate `id`. A page test can call `check(client, url)`
  after it adds rows.

### Changed

- `stario-auth` (4 KB) and `stario-tailwind-daisyui` (4 KB) run the kit and
  explain the files. They no longer hold the code. `stario-login` is gone.
- A browser is for two cases only: client JavaScript that holds state, and
  a bug that `curl` and a test show as correct. `AGENTS.md` says no
  computer use. `stario-browser-check` maps each question about a page to
  its test.

## 5.6.0

### Changed

- Every skill fits in 9 KB. Devin's skill tool shows a skill inline at
  9.0 KB and returns only a pointer at 15 KB, so the agent read
  `stario-feature` (31 KB) and `stario-auth` (15 KB) in two or three more
  calls. A test now holds the limit.
- `stario-feature` is split by the words of the task:
  - `stario-feature`: a live page in SQLite on `db.watch`, its stream tests
    (two streams are two tabs), a command that goes to the page it made,
    removing a page, and a folder that grew.
  - `stario-view`: a sort, a filter, or paging in the URL, and search as
    you type.
  - `stario-relay`: a complete live page in memory, messages to one tab,
    the edit dialog, and a value one tab remembers.
  - `stario-jobs`: slow work as a complete page, with its test.
  - `stario-browser-check`: the `TestClient` test for each question about
    HTML, the order to find a bug, and the Playwright script.
- `stario-auth` is split into `stario-auth` (the session, the `Config`
  fields, the wiring, protected pages) and `stario-login` (the users
  table, the login page, sign-up, logout, and the tests).
- `AGENTS.md` opens with `## Which skill`: the skill for each task, and
  `stario-api` before any code. A static page needs no skill.
- `stario-api` and `stario-litewriter` are shorter. Every signature stays.

### Fixed

- `AGENTS.md`, Commands, step 4 said that every command publishes. A
  stream on `db.watch` needs no publish.
- The slow-work and edit-dialog examples were fragments. They are now
  complete files, and every example of the split skills passed
  `just check` in a new app.
- The view example rejected a bad tab id with a message about the title.
- `stario-litewriter` and the view example now use the same names.
- `stario-tailwind-daisyui` no longer sends a class question to a browser
  or to computer use.

## 5.5.0

### Changed

- One API skill: `stario-api` replaces `stario-datastar`. It holds every
  signature an agent needs — App, Route, Context (`c.req.query` is a
  `ParsedQuery`), headers, cookies, Writer, Relay, Span, middleware
  (`security_headers()` sets no CSP), `STARIO_HOST`/`STARIO_PORT`, `h.*`
  tags as rules, TestClient, `data.*`, `at.*`, `read_signals`, `SSE`, and
  how a morph treats the page. Evals showed agents load one or two skills
  per task, so a split API skill was missed and they read `site-packages`.
- `stario-feature` tells the agent to load `stario-api`, and drops its
  own API card. `stario-client` and `stario-tailwind-daisyui` point to it.
- Simpler defaults, learned from the apps in production: most pages have
  no sort or filter and never message one tab. The guide makes the `View`
  and the tab id optional, names `db.watch` as the common stream, and asks
  for a busy indicator on forms, not on every button. `stario-feature`
  opens with the plain watch page (no view, no tab, no Relay), then adds
  the view and tab messages.
- `stario-litewriter` has a full `watch` section: what wakes it (only the
  columns its query reads), `into`, parameters, one fixed SQL text per
  sort key (`ORDER BY` cannot be a parameter), and how to test it.

## 5.4.0

### Changed

- The guide has a `## Checks` section. An agent checks a change at the
  cost that it needs: a `TestClient` test for logic, `just css` for a
  style, and `just check` after a Python change and before a push. It
  trusts Stario, Datastar, litewriter, and Tailwind. A browser is only
  for client JS that holds state, a new layout, or a browser bug that no
  test reproduces. When the user watches the app in the chat, the user
  is the browser.
- `stario-feature` replaces the Playwright section with "Browser check":
  a script that starts its own server on a free port, stops it in
  `finally`, and has a 60 s limit.
- New skill `stario-datastar`: every `data.*`, `at.*`, and `SSE`
  signature from the stario source, the Datastar Pro-only list, and how a
  morph treats the page. Agents no longer read `site-packages` for a
  signature; the guide says pyright checks each call.
- `stario-feature`'s API card drops `data.persist()`. It is Datastar Pro
  only, and the apps ship the free bundle.
- Checks are looser: a new layout no longer needs a browser or a
  screenshot. A browser is only for client JS that holds state, or a
  browser bug that no test reproduces.
- `sync --check` exits 1 when `AGENTS.md` is over 16,000 bytes, where
  rule loaders cut an always-on file.
- The guide drops repeated text to stay under the 12 KB budget: the
  shutdown details (still in `stario-feature`, slow work) and three rows
  of Common mistakes that repeat a rule above them.

## 5.3.4

### Fixed

- The busy indicator sits on the element whose `data.on` sends the
  request. `data.indicator` on a submit button inside a `data.on("submit")`
  form never fires, since the fetch belongs to the `<form>`. The guide
  rule, the Add and Save examples, and the API card now place it on the
  sending element; a new test guards the pattern in skill code blocks.

## 5.3.3

### Added

- The guide allows a `POST` for a private read when the input is too long
  for a URL; it still changes no state and keeps nothing.
- The guide requires a busy indicator on every button that sends a
  command: `data.indicator("_saving")` and `data.attr("disabled",
  "$_saving")`. The stario-feature examples show it.
- `stario-feature`'s API card gains `c.span`, the `datastar-request`
  header check, `STARIO_HOST`/`STARIO_PORT`, `data.on` modifiers,
  `data.persist`, and `stario.markup.svg` — all verified against stario
  5.2.0.
- `stario-litewriter` gains `## API at a glance`: LiteWriter open/close,
  write/push/submit, query/one/value and their async forms, `watch`, and
  `apsw.ConstraintError` — verified against litewriter 0.3.2.
- `evals/check.py` reports `private_posts`: a non-GET handler that
  renders without mutating is a private read, not a bad command.
  `evals/summary.py` shows it as `priv`.

## 5.3.2

### Added

- The guide documents route precedence: a literal segment beats a
  parameter in any registration order, so `/rooms/live` and
  `/rooms/{room_id}` both work. Same line in `AGENTS-api.md`.
- `stario-feature` gains `## API at a glance`: the names and keywords an
  agent needs (App, Context, Writer, `read_signals`, `SSE`, `data.*`,
  `at.*`, `h.*`, Relay, Span, TestClient), verified against stario 5.2.0.

### Fixed

- `stario-create new` no longer ships a dead package. uv 0.13.5's
  `uv init --app` creates `src/<name>/`, `[project.scripts]`, and
  `[build-system]`; the scaffold now passes `--no-package`, so a new app
  keeps every file in `app/` where pyright and the guide look.
- The Tailwind skill pins the DaisyUI tag it was tested with,
  `DU=v5.7.50`, instead of `v5.x.y`.

## 5.3.1

### Fixed

- The scaffold keeps its files where Yard keeps them. `Config` gets
  `data_dir`: `$PROJECT_DATA_DIR`, or `./data` when it is unset, created
  on start. `db_path` is `data_dir / "app.sqlite3"`. Yard sets
  `PROJECT_DATA_DIR=/data`, so a deployed database survives every deploy;
  before, `app.sqlite3` sat in the container and a redeploy lost it.
  `APP_DB_PATH` is gone. `tests/conftest.py` sets `PROJECT_DATA_DIR` to
  `tmp_path`, `.gitignore` gets `data/`, and the guide, `stario-litewriter`,
  and `stario-auth` follow.

## 5.3.0

### Added

- A new skill, `stario-client`: server first, then HTML and CSS, then a
  Datastar attribute, then a function in `static/js/<name>.js`. Each file
  is a classic script that defines one `app.<name>` namespace — a plain
  object literal, or a per-element factory only when the element needs
  its own state. Datastar adds every page-wide listener with
  `data.on(..., target="window")`.

### Changed

- The guide drops "No `.js` files". JavaScript lives in
  `static/js/<name>.js`, never in a Python string; the guide points to
  `stario-client` and stays under the 12,000-byte budget.
- `assets.py` gets `SCRIPTS`: a tuple of `ASSETS.href("js/<name>.js")`.
  The shell loads each one with `h.Script({"src": src, "defer": True})`
  before `ModuleScript(DATASTAR_JS)`.
- `new` writes `tests/test_js.py`: every `app.<name>.<method>` call in
  `app/**/*.py` must have its function in `static/js/<name>.js`.
- `stario-feature`'s edit dialog uses `data.ref` (`$_edit.showModal()`),
  not a `getElementById` in the expression.
- `stario-tailwind-daisyui` keeps the one-line theme restore as the only
  inline script and moves the toggle to `theme.js` (`app.theme`). Its
  shell example loads `SCRIPTS` before Datastar, same as the scaffold.
- `evals/check.py` probes for JavaScript in `app/**/*.py`
  (`addEventListener`, `getElementById`, `window` writes, arrow bodies,
  `h.Script(SafeString(`) and, in `static/js`, window or document
  listeners and HTML building.
- README and `llms.txt` list `stario-client` with the other skills.
- The guide proves a live update from the next SSE event (`timeout=2` on
  `client.stream`, so a missing repaint fails in two seconds). Playwright, in
  the `stario-feature` skill, checks that Datastar morphed that HTML. A
  computer-use session is for a visual judgment the assertion cannot make.
  The guide stays under 12,000 bytes.

### Changed: pages, commands, and storage

- A page is a resource. The path names it; a `View` dataclass in
  `urls.py` reads and writes the query (sort, filter, columns). The page
  and the stream read the same view, so a link or a reload shows the
  same thing. "Screen" is now "page" in the guide and the skills.
- A page is one class in `handlers.py`: its fields are its dependencies,
  `register(app)` adds the routes, and each route is one method. The
  handler factories and `register_<screen>` functions are gone. The
  scaffold's `home` is `HomePage`.
- A command reads, validates, replies, and then executes. The HTTP status
  is the reaction of the browser; the span records the outcome of the
  work. The default is `await db.write(...)` after the reply; `db.push`
  is only for a write that nothing reads soon after.
- The signals are the state of one tab. A command that tells its tab
  something after the work publishes signals on `tab.<id>`, and the
  stream sends them with `patch_signals`. The app has one `Relay[dict]`:
  `CHANGED` carries `{}`. A domain conflict is no longer written to
  shared state, and a command never answers with HTML.
- The scaffold's shell has a `_toast` signal and an `<output>` that shows
  it for 4 seconds. A signal bound with `data.text` or `data.show` keeps
  its value through a repaint, so no `ignore_morph` is needed.
- `execute_script` is for an action, not for text. A server value in it
  goes through `string_literal`, which escapes `<` from stario 5.2.
- New apps require `stario>=5.2`: `TestClient` signals shutdown on exit
  and cancels a job after 5 s, so a job test cannot hang.
- A job runs in its own span (`c.span.step(...)`), marks itself failed
  on `CancelledError`, and stops at shutdown. A job row in SQLite is
  marked failed when the app starts.
- The guide names the layers not to build (service classes, command and
  result objects, repositories, `utils`) and says where the code goes
  instead. It gives one line for each repeated input read.
- SQLite tables are `id` plus `data` JSON. A filtered, sorted, or unique
  field is a virtual column with an index; add and drop virtual columns
  instead of migrating data. Needs litewriter 0.3.2.
- `stario-auth` uses litewriter, runs scrypt in `asyncio.to_thread`, and
  refuses to start with `ADMIN_EMAIL` and a short or empty
  `ADMIN_PASSWORD`. The login answer is a signal, not HTML.
- The tests drop the `accept-encoding: identity` header (`TestClient`
  sends no `Accept-Encoding`) and use `TestClient(bootstrap,
  request_timeout=5)`.

### Fixed

- `tests/test_js.py` no longer reads the string `"app.sqlite3"` as a call
  to `app.sqlite3`. A fresh app failed `just check`.
- The package tests parse every Python block in every skill.

## 5.2.0

### Changed

- `new` no longer writes a `Dockerfile`. Yard detects a Stario app from
  `pyproject.toml` and `uv.lock` and writes the Containerfile itself. `new`
  still writes `.dockerignore`, which that build uses.

## 5.1.3

### Changed

- The app Dockerfile copies uv 0.13.5. uv below 0.13.4 still trusts the
  compromised emSign root while it downloads packages.

## 5.1.2

### Added

- `stario_create.data_dir()` returns the folder with `AGENTS.md`,
  `AGENTS-api.md`, `llms.txt`, and `skills/`. A site that serves these
  files reads them from there.

## 5.1.1

### Added

- The `justfile` has a `sync` recipe: `uvx stario-create@latest sync`.
- Cloud Agent files: `.cursor/environment.json` and `.cursor/cloud-install.sh`.
  `new` writes them. `sync` writes a missing `environment.json` and keeps
  `cloud-install.sh` current. The install script puts `uv`, Python 3.14, and
  `just` on the disk.
- `.cursor/cloud-install.sh` installs the dependencies from `uv.lock`
  (`uv sync --all-groups --all-extras --locked`, with a fresh resolve when the lock is
  stale) and runs `just tailwind` when the app has that recipe.
- The guide has a `Cursor Cloud specific instructions` section. The stream
  test is the proof. Use computer use only when that cannot prove the change.
- `stario-feature`, `stario-auth`, and `stario-litewriter` tell the agent to
  prove a change with `TestClient`, not a browser. The feature skill now has
  the live-screen stream test.
- An app profile: `[tool.stario-create] profile = "api"` in the app's
  `pyproject.toml` gives the app the short JSON API guide and no skills.
  `sync` removes the skills the profile excludes.
- `sync --check` also reports agent files that git ignores and a `check`
  recipe that does not run pytest.
- `new` writes a `Dockerfile` and a `.dockerignore`. The image installs
  from `uv.lock` and listens on `0.0.0.0:8000`.

### Changed

- The guide no longer says how to deploy: no "push `main`", no "do not open
  a pull request". That workflow belongs in the app's `## This app` notes.
- `sync` always refreshes `.cursor/cloud-install.sh`; the file is tool-owned.
  `.cursor/environment.json` is still only written when missing.
- The Tailwind skill puts a `tailwind` recipe in the `justfile`. `css` and
  `css-watch` run it first. It downloads the pinned binary once per version
  into `~/.cache/tailwindcss/`.

## 5.1.0

### Added

- `stario-create new --orjson` adds `orjson` to the app's dependencies and
  sets it as the `stario.json` codec in the scaffolded `main.py`.

### Changed

- The guide (`AGENTS.md`) is rewritten and much shorter, so it fits the rule
  budget of an agent. It sorts every user action into three kinds — go
  somewhere, ask for something only this tab needs, change shared state — and
  shows when a screen needs a stream. A stream route is `/live`, not
  `/subscribe`.
- Signals are for inputs, forms, and client-only state. Per-tab view state
  (sort, filter, page) lives in the URL query, and one signal per field plus
  `editing_id` replaces one signal per row. `data.indicator` covers request
  state; `data.preserve_attr` keeps a user-opened dialog open across a morph.
- `sync` now replaces the guide (`## This app` is kept byte for byte) and
  installs the skills and their `.claude/skills` links. `sync --check` exits 1
  when the guide or a skill is stale.
- A handler that needs nothing is a plain `async def`. A factory exists only
  to close over dependencies.
- New apps require `stario>=5.1,<6`. The scaffold's `bootstrap` applies
  `same_origin()` and `security_headers()`. The guide and the skills use 5.1:
  leading-underscore signal names, `relay.subscribe(..., latest=True)` for
  repaint streams, and the `httponly`/`samesite` cookie defaults.
- The `stario-litewriter` skill targets litewriter 0.3 (`uv add
  "litewriter>=0.3,<0.4"`): `schema=` on `LiteWriter`, `await db.write`,
  build-once statements with name lists (`columns=`, `set=`), the positional
  row builder, `ClaimBusy`, and `apsw.ConstraintError` for a taken unique
  value. The auth skill and the eval fixture use the same API.
- The scaffolded `justfile` sets `dotenv-load`, so a local `.env` is loaded
  for `just` recipes.
- Skills:
  - `stario-feature` also covers changes to a screen: a button, a dialog, a
    search box, a job, a page that does not repaint. It holds the complete
    example files.
  - `stario-auth` shows the store functions in litewriter form and has a
    section for adding accounts to an app that already has screens: keep the
    URLs, ask what happens to rows that exist before accounts, and filter
    every query by `c.state["user"]`.
  - `stario-tailwind-daisyui` pins the downloaded versions and adds a
    light/dark theme switch recipe.

### Added

- `evals/` — a harness that runs headless agents against the guide and the
  skills on twelve tasks and checks the result (`setup.sh`, `batch.sh`,
  `check.py`, `summary.py`).
- `tests/test_guide.py` — checks the guide size, the syntax and formatting of
  its Python blocks, and that it ends with `## This app`.

### Removed

- **Breaking:** the `init`, `screen`, `skills`, `guide`, `dev`, `serve`,
  `check`, `fix`, `test`, and `version` subcommands. Only `new`, `sync`, and
  `--version` remain. The `justfile` runs development and quality tasks; the
  `stario-feature` skill replaces `screen`.
- **Breaking:** the `--json`, `--text`, and `--dry-run` flags. Output is plain
  text.
- The screen templates and `tasks.py`.

## 5.0.1

- Dev reload runs the app as `watchfiles`' direct child.
- `uvx stario-create` is the one entry point; `setup.sh` is gone.
- Publish to PyPI on GitHub releases through trusted publishing.

## 5.0.0

- First public release: `new`, `init`, `screen`, `skills`, `guide`, task
  commands, the `AGENTS.md` guide, and the four skills.
