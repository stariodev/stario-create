"""ablate.py -> cost and quality per variant and task, from $EVAL_DIR/runs/<variant>-<task>-<n>-<model>.

Cost: wall seconds, steps, prompt tokens (total and uncached), completion tokens,
guide bytes the agent loaded (skill tool + read of a SKILL.md), and source dives into site-packages.
Quality: `just check` passes, plus the drift that the guide forbids.
"""

import contextlib
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

root = Path(os.environ.get("EVAL_DIR", "/tmp/stario-eval")) / "runs"
VARIANTS = ["full", "guide", "skills", "none"]


def tool_calls(run: Path) -> list[tuple[str, dict, int]]:
    """(name, arguments, characters of the tool result) for each call."""
    try:
        d = json.loads((run / ".eval-transcript.md").read_text())
    except OSError, json.JSONDecodeError:
        return []
    out = []
    for s in d.get("steps") or d.get("trajectory") or []:
        sizes = {
            r.get("source_call_id"): len(str(r.get("content") or ""))
            for r in (s.get("observation") or {}).get("results") or []
        }
        for tc in s.get("tool_calls") or []:
            name = (
                tc.get("function_name") or tc.get("name") or (tc.get("function") or {}).get("name")
            )
            args = tc.get("arguments") or (tc.get("function") or {}).get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            out.append(
                (
                    name or "?",
                    args if isinstance(args, dict) else {},
                    sizes.get(tc.get("tool_call_id"), 0),
                )
            )
    return out


def measure(run: Path) -> dict:
    c = json.loads((run / ".eval-check.json").read_text())
    fm = {}
    with contextlib.suppress(OSError, json.JSONDecodeError):
        fm = json.loads((run / ".eval-transcript.md").read_text()).get("final_metrics") or {}
    calls = tool_calls(run)
    guide_kb = 0
    skills_used = []
    dives = 0
    for name, a, size in calls:
        text = json.dumps(a)
        if name == "skill" and a.get("skill"):
            skills_used.append(a["skill"])
            guide_kb += size
        elif name in {"read", "exec", "grep"} and ("SKILL.md" in text or "AGENTS.md" in text):
            guide_kb += size
            hit = re.search(r"skills/([\w-]+)/SKILL\.md|AGENTS\.md", text)
            skills_used.append(f"{name}:" + (hit.group(1) or "AGENTS.md" if hit else "?"))
        if "site-packages" in text:
            dives += 1
        if name == "exec" and "stario-create" in text and ("sync" in text or "new" in text):
            skills_used.append("SELF-SYNC")
    drift = [
        k
        for k, bad in [
            ("no_page_class", c.get("page_class") is False),
            ("factories", bool(c.get("handler_factories"))),
            ("layers", bool(c.get("layer_classes"))),
            ("renders_in_cmd", bool(c.get("commands_that_render"))),
            ("globals", bool(c.get("module_mutable_state"))),
            ("environ", bool(c.get("environ_outside_config"))),
            ("asyncio_task", bool(c.get("bare_asyncio_create_task"))),
            ("js_in_py", bool(c.get("js_in_python") or c.get("inline_script"))),
            ("url_for", bool(c.get("url_for"))),
        ]
        if bad
    ]
    return {
        "ok": c.get("check_all"),
        "fail": [k for k, v in c.get("check", {}).items() if not v],
        "tests": c.get("tests_passed", 0),
        "sec": c.get("seconds"),
        "steps": fm.get("total_steps"),
        "ktok": round(fm.get("total_prompt_tokens", 0) / 1000),
        "kuncached": round(
            (fm.get("total_prompt_tokens", 0) - fm.get("total_cached_tokens", 0)) / 1000
        ),
        "kout": round(fm.get("total_completion_tokens", 0) / 1000, 1),
        "calls": len(calls),
        "guide_kb": round(guide_kb / 1000),
        "skills": skills_used,
        "dives": dives,
        "drift": drift,
        "store": c.get("store"),
        "live": c.get("has_live_route"),
    }


runs: dict[tuple[str, str], list[dict]] = defaultdict(list)
for f in sorted(root.glob("*/.eval-check.json")):
    m = re.match(r"(full|guide|skills|none)-(T\d+-[a-z]+)-(\d+)-", f.parent.name)
    if not m or m.group(3) == "0":
        continue
    try:
        runs[(m.group(1), m.group(2))].append(measure(f.parent) | {"n": int(m.group(3))})
    except json.JSONDecodeError, KeyError:
        print("broken", f.parent.name, file=sys.stderr)

if "--runs" in sys.argv:
    for (v, t), rs in sorted(runs.items(), key=lambda kv: (kv[0][1], VARIANTS.index(kv[0][0]))):
        for r in rs:
            print(
                f"{t:11} {v:6} n{r['n']} ok={r['ok']!s:5} sec={r['sec']!s:>4} steps={r['steps']!s:>3} "
                f"ktok={r['ktok']:>5} unc={r['kuncached']:>4} out={r['kout']:>5} guide_kb={r['guide_kb']:>3} "
                f"dives={r['dives']:>2} tests={r['tests']:>2} fail={','.join(r['fail']) or '-'} "
                f"drift={','.join(r['drift']) or '-'} store={r['store']} live={r['live']} skills={','.join(r['skills']) or '-'}"
            )
    print()

med = statistics.median
print("per variant, over all tasks (median of per-task medians for cost; counts for quality)")
print(
    f"{'variant':7} {'runs':>4} {'ok':>5} {'drift':>5} {'sec':>5} {'steps':>5} {'ktok':>6} {'unc':>5} {'out':>5} {'gkb':>4} {'dives':>5}"
)
for v in VARIANTS:
    per_task = [rs for (vv, _), rs in runs.items() if vv == v]
    allr = [r for rs in per_task for r in rs]
    if not allr:
        continue

    def m(key: str, tasks: list = per_task) -> float:
        return med(med(r[key] or 0 for r in rs) for rs in tasks)

    print(
        f"{v:7} {len(allr):>4} {sum(bool(r['ok']) for r in allr):>2}/{len(allr):<2} "
        f"{sum(bool(r['drift']) for r in allr):>5} {m('sec'):>5.0f} {m('steps'):>5.0f} {m('ktok'):>6.0f} "
        f"{m('kuncached'):>5.0f} {m('kout'):>5.1f} {m('guide_kb'):>4.0f} {m('dives'):>5.0f}"
    )

print("\nper task: median seconds / median ktok / ok count, by variant")
tasks = sorted({t for _, t in runs}, key=lambda t: int(t[1:].split("-")[0]))
print(f"{'task':11} " + " ".join(f"{v:>18}" for v in VARIANTS))
for t in tasks:
    cells = []
    for v in VARIANTS:
        rs = runs.get((v, t), [])
        cells.append(
            f"{med(r['sec'] or 0 for r in rs):>5.0f}s {med(r['ktok'] for r in rs):>5.0f}k {sum(bool(r['ok']) for r in rs)}/{len(rs)}"
            if rs
            else "-"
        )
    print(f"{t:11} " + " ".join(f"{c:>18}" for c in cells))
