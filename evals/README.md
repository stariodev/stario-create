# evals

Which guide+skills variant makes a headless agent build the better app:
scaffold a base app, install a variant's `AGENTS.md` and `skills/`, run one
`devin -p` task, score the result with `check.py` (ruff/format/pyrefly/pytest
plus structure rubric). Runs live under `$EVAL_DIR` (default /tmp/stario-eval).

```sh
./setup.sh                          # creates $EVAL_DIR/evalapp
STARIO_PATH=../stario ./setup.sh    # also evalapp-local/-todos/-todos-bug
STARIO_PATH=$PWD/../../stario LITEWRITER_PATH=$PWD/../../litewriter ./setup.sh  # unreleased versions
./batch.sh current swe-2-high T1-todos:1 T4-about:1   # `current` = this repo
python3 summary.py                  # one row per run
```

T8–T12 edit an existing screen: `BASE=evalapp-todos` (`BASE=evalapp-todos-bug` for T10).
T11 (accounts) reports an `auth` block and T12 (Tailwind, theme switch) a `style` block.
`wrapper_factories` lists factories that take nothing: redundant, reported, never a failure.
`page_class` is true when `handlers.py` has a `*Page` class with `register`. `handler_factories` lists
old-style factories, and `layer_classes` lists service, command, or result classes: the drift the guide
forbids. `view_from_query` (T8) and `tab_channel` show whether the view is in the URL and whether a
command answers its own tab through the stream.
