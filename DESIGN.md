# Kit design (6.0)

The kit is `AGENTS.md` (always on), seven skills (loaded on demand) and the `stario-create`
tools. It was written from the brief in stario-agent-bench `notes/kit-learnings.md`, not from
the 5.x text. The readers are Haiku 5.5 and Sonnet 5.5 in Claude Code. Cost is steps.

## What is always on, and why

Each always-on line is paid on every step and dilutes attention. A fact that most apps need
and that sits in a skill gets probed or guessed. So `AGENTS.md` (11.9 KB, under the 12 KB that
leaves 4 KB of app notes under the 16 KB rule-loader cut) holds what a first app needs and
nothing else:

1. **The loop** in six steps: start with kits in one command, read spec and tests, write the
   files in a fixed order, `check`, `request`, run the suite in the foreground and stop when it
   passes. The shell facts (no `timeout`, `sed -i ''`, stop by port, `STARIO_PORT=$PORT`) sit
   under it, because the habits they replace cost runs in every round.
2. **One complete page** (urls, data, page module) that covers the most needed shapes at once:
   a list read from the URL query (search and paging), a live stream (`db.watch` + `c.alive`),
   a Datastar command with validation, a plain GET form. Code examples are the part of docs that
   helps most with an unknown library.
3. **Names**: one fact per line for what the example does not show (answers, plain forms,
   routes, search as you type, row buttons, static files that keep their name, cookies, JSON,
   settings).
4. **Rules that bite**: the facts that raise or silently misbehave (`@baked`, writes without
   network or hashing, what `watch` wakes on, `ORDER BY`, no redirect from an action, generated
   tests).
5. **Accounts** through the kit (six lines): enough for sign-up, sign-in, protected pages.
6. **Skills**: one paragraph that routes each task to one skill.

Left out of the always-on file on purpose: `add page` (used 0/12 in round 3), `just` (absent on
the bench host; `uvx stario-create@latest check` works everywhere), the browser, Tailwind
details (the kit's printed `next:` lines carry them), test writing (a skill, and only without an
acceptance suite: always-on test text made agents write hundreds of lines nobody asked for).

## Skills: seven, one per task, no chains

| Skill | Task |
| --- | --- |
| `stario-tests` | write TestClient tests (no acceptance suite, or tests asked for) |
| `stario-migrate` | change tables that already hold rows |
| `stario-outside-api` | read another service over HTTP |
| `stario-js` | write JavaScript; the rare browser check |
| `stario-background` | state in memory (Relay), slow jobs with progress, timers |
| `stario-accounts` | accounts past the kit: Google setup, signed-in header, owned rows, roles, tokens |
| `stario-reference` | every other name, for when the guide lacks one or pyrefly rejects one |

Split by task, not by API area, so a task matches one skill: 5.x's `stario-jobs` built on
`stario-relay` (both always loaded) and they are now one; `stario-auth` sent agents on to
`stario-litewriter` (6/6 runs, used in none). No skill points to another skill except for one
case it does not cover (a test checks this). No skill has `references/`: a reference costs a
second step, and every skill fits in 8 KB.

Gone: `stario-view` (sort, filter, paging and search are in the always-on page),
`stario-tailwind-daisyui` (the kit's output says what to do), `stario-browser-check` (the loop
says "no screenshots"; the browser kit is in `stario-js`), `stario-feature`, `stario-datastar`,
`stario-api` (split between the guide, `stario-tests` and `stario-reference`). `sync` removes
the retired skill folders from an app.

Descriptions put the task's own words first, then "Use when ...", and say what the skill is not
for where a neighbour is close ("Not when the task ships its own suite"; "Not for the tables of
a new app"; "Not for what data.* attributes already do").

## Prose rules replaced by tools

| Rule that agents broke | Now |
| --- | --- |
| A form-based spec rewrites the password kit's Datastar login and breaks `test_login.py` (6/6 Conduit runs) | The kit's login and sign-up pages are plain HTML forms; `test_login.py` checks behaviour (status, session, redirect), not wording, so paths, labels and markup can change freely |
| `DATABASE_PATH` from the env needs a Config field and a `db_path` that honours it | The scaffold's `Config` (and both auth kits') has `database_path`; `db_path` uses it when set. `conftest.py` and `request` clear it, so tests stay isolated |
| `w.redirect` defaults to 307 | lint `redirect-status`: a redirect without a status is a finding with the fix |
| `classes()` is never a dict value | lint `classes-in-dict` (pyrefly's message was cryptic) |
| `ORDER BY :param` | lint `order-by-param` |
| `kill $!` reaches no job of an earlier call | the `pkill` lint message says stop by port |
| `new` told agents to "write every page in one step" | `new` ends with the next steps of the loop: kits first, then the files, then `check` |

Still prose, because no tool can hold them: the foreground suite, no `pkill -f` in a Bash call,
no `timeout`. They are one sentence each, next to the step they belong to.

## The loops

- **New app, acceptance suite**: `new` with kits, read spec and tests, write in order, `check`
  until ok, suite in the foreground until green, stop.
- **New app, no suite**: the same, then `stario-tests`, `check`.
- **Change an app that holds data**: read urls, data and the pages first; `stario-migrate` for
  any table with rows; `check`; the suite.

## Probe cases

`evals/cases/*.jsonl` name the skills of 5.x. The skill names were changed to the 6.0 routing,
and no code pattern was touched:

- `stario-litewriter` → `stario-migrate`; `stario-relay`, `stario-jobs` → `stario-background`;
  `stario-client`, `stario-browser-check` → `stario-js`; `stario-feature` → `stario-tests`;
  `stario-auth` → `stario-accounts`; `stario-api`, `stario-datastar`, `stario-view` →
  `stario-reference`.
- Cases now answered by the always-on file need no skill: `accounts-password` (ok:
  `stario-accounts`), `sort-filter`, `search-typing`, `tailwind`, `screenshot` (ok: `stario-js`).
- `google-signin` needs `stario-accounts` (the signed-in header); `edit-dialog`, `navbar-count`,
  `infinite-scroll` need `stario-reference`.

Three `decide.jsonl` cases encode 5.x answers this kit changes on purpose: `d-page-file` expects
`add page`, `d-stop-server` expects `kill $!` (the brief says it fails across tool calls), and
`d-env-setting` expects the agent to add the `database_path` field that the scaffold now has.
