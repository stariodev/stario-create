# evals

Cheap checks of the guide (`AGENTS.md`) and the skills, run before a kit change
goes to the full benchmark ([stario-agent-bench](https://github.com/stariodev/stario-agent-bench)).

Three levels, cheapest first:

| Level | What it measures | Cost | Command |
| --- | --- | --- | --- |
| Free | Size budgets, frontmatter, every example parses, formats and type-checks, each lint rule | none | `uv run pytest` |
| Probe | Routing: does the right skill load before code is planned, and is the planned code right? Clarity: does a narrow question get the guide's answer, every time? | $0.01–0.10 a run | `evals/probe.py` |
| Bench | Whole apps (Conduit, Pokédex, changing Conduit) against other frameworks | $1–3 a build | the bench repo |

## Probes

`probe.py` scaffolds an app once per kit version (`stario-create new app --db`),
then runs `claude -p` once per case in a fresh copy of it. The agent sees what
an agent in a real app sees: `CLAUDE.md` → `AGENTS.md`, and the skills in
`.claude/skills/`. Its tools cannot change a file (Read, Glob, Grep, Skill, and
read-only shell commands), so a probe never builds or runs anything; it ends
with the agent's reply. User settings, hooks, plugins and MCP servers are left
out (`--setting-sources project --strict-mcp-config`).

```sh
evals/probe.py evals/cases/route.jsonl --model claude-haiku-5-5 -n 3
evals/probe.py evals/cases/route.jsonl --model claude-sonnet-5-5 -n 2
evals/probe.py evals/cases/decide.jsonl --model claude-opus-5-5 --effort '' -n 3
evals/probe.py evals/cases/route.jsonl --kit ../other-checkout   # another kit version
evals/probe.py --report evals/runs/probe/<run>                   # the table again
```

Two case files:

- `cases/route.jsonl`: a feature request, planned in full. The case names the
  skills that must load (`"skills"`), may load (`"ok_skills"`) or must not load
  (`"not_skills"`), and regexes the planned code must or must not contain
  (`"has"`, `"lacks"`). Run on Haiku and Sonnet, the models that build apps.
- `cases/decide.jsonl`: one narrow question with one right answer ("what does
  the handler reply when the row is missing?"). Run on Opus, several times: a
  wrong answer, or an answer that changes between runs, marks text that is
  wrong or unclear. A model this strong getting it wrong is a text problem,
  not a reader problem.

`"base": "todos"` starts a case from `fixtures/todos/`: the scaffold plus the
todos page of `AGENTS.md`, for requests that change an app with data.

Each run writes `evals/runs/probe/<kit>-<cases>-<model>-<time>/`: one JSON file
per run (skills loaded and at which step, files read, cost, the reply), the raw
stream, and `summary.md`.

## Comparing two kit versions

Check out the baseline next to this one (`git worktree add ../base main`), run
the same case file with `--kit ../base` and without, and compare the two
`summary.md` tables: pass rate per case, routing (expected loads that
happened, loads no case asked for), and median cost. Read the replies of the
cases that changed. A change goes to the benchmark only when no case got worse.

## Tasks

`tasks/` holds small build prompts (a todos page, search, accounts, a bug to
fix). They seed new probe cases, and they are the prompts to use for a quick
build check by hand: `stario-create new`, the task, `just check`.
