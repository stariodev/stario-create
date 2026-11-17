#!/usr/bin/env python3
"""probe.py: cheap, read-only agent probes of the guide and skills.

Each case runs `claude -p` once in a fresh copy of a scaffolded app (AGENTS.md
loaded through CLAUDE.md, skills in .claude/skills) with tools that cannot
change a file. The probe records which skills and references the model loaded,
what it read, its turns and cost, and checks its final reply against the case's
patterns. No app is built: a probe measures routing (did the right skill load
before code was planned) and clarity (did the text lead to the right decision).

    evals/probe.py evals/cases/route.jsonl --model claude-haiku-5-5 -n 3
    evals/probe.py evals/cases/decide.jsonl --model claude-opus-5-5 -n 3
    evals/probe.py CASES --kit ../other-checkout   # another guide and skills
    evals/probe.py --report runs/probe/<run dir>   # the table again

A case is one JSON line:
    id        unique name
    prompt    what the agent is asked
    mode      "plan" (default: the reply is the full code it would write) or
              "answer" (the reply is a short answer, for decision questions)
    skills    skills that must load; "a|b" means either
    not_skills  skills that must not load
    has       regexes the reply must match (Python re, MULTILINE)
    lacks     regexes the reply must not match
    base      "new" (default) or a fixture folder under evals/fixtures/ copied
              over the scaffold (an app that already has code)
    suite     plan cases say the task ships an acceptance suite, as the benchmark's
              tasks do; false leaves that out (a case that asks for tests)

Output: runs/probe/<kit>-<cases>-<model>-<time>/ with one JSON file per run
(the stream is kept as .jsonl) and summary.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT_DEFAULT = HERE.parent
CACHE = Path(os.environ.get("PROBE_CACHE", Path.home() / ".cache" / "stario-create-probe"))

PLAN = (
    "\n\nThis is a planning step: do not create or edit any file and run nothing that "
    "changes the app. Reply with every file you would write or change, each as its path "
    "and its full code."
)
# Like the benchmark's tasks, a plan case ships an acceptance suite unless it says "suite": false.
SUITE = "\n\nThe task ships an acceptance suite (`npm test`) that checks the result."
ANSWER = "\n\nAnswer from this app's guidance. Do not create or edit any file. Reply briefly."

READ_ONLY = ["Read", "Glob", "Grep", "Skill", "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)",
             "Bash(head:*)", "Bash(find:*)", "Bash(wc:*)"]
NO_WRITE = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent"]
SKILL_PATH = re.compile(r"skills/(stario-[a-z-]+)/(SKILL\.md|references/([\w.-]+))")


def kit_hash(kit: Path) -> str:
    h = hashlib.sha256()
    for p in sorted([kit / "AGENTS.md", *kit.glob("skills/**/*.md"), *kit.glob("src/**/*")]):
        if p.is_file():
            h.update(str(p.relative_to(kit)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def base_app(kit: Path) -> Path:
    """A scaffolded app for this kit, made once and cached by the kit's content."""
    dest = CACHE / f"base-{kit_hash(kit)}"
    if (dest / "app" / "AGENTS.md").exists():
        return dest / "app"
    tmp = Path(tempfile.mkdtemp(prefix="base-", dir=CACHE.mkdir(parents=True, exist_ok=True) or CACHE))
    subprocess.run(
        ["uvx", "--no-cache", "--from", str(kit), "stario-create", "new", "app", "--db", "--no-verify"],
        cwd=tmp, check=True, stdout=subprocess.DEVNULL,
    )
    shutil.rmtree(tmp / "app" / ".venv", ignore_errors=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp / "app", check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp / "app", check=True)
    subprocess.run(["git", "-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
                    "commit", "-qm", "scaffold"], cwd=tmp / "app", check=True)
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    return dest / "app"


def clean_env(tmpdir: Path) -> dict[str, str]:
    claude = shutil.which("claude") or "claude"
    uv = shutil.which("uv") or "uv"
    path = [str(Path(claude).resolve().parent), str(Path(uv).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return {
        "HOME": str(Path.home()), "USER": os.environ.get("USER", ""), "LANG": "en_US.UTF-8",
        "SHELL": "/bin/bash", "TERM": "xterm-256color", "TMPDIR": str(tmpdir),
        "PATH": ":".join(dict.fromkeys(path)), "DISABLE_AUTOUPDATER": "1",
    }


def parse_stream(lines: list[str]) -> dict:
    loads: list[dict] = []
    reads: list[str] = []
    tools: list[str] = []
    step_ids: list[str] = []
    result: dict = {}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant" and not e.get("parent_tool_use_id"):
            msg = e["message"]
            if msg["id"] not in step_ids:
                step_ids.append(msg["id"])
            step = len(step_ids)
            for b in msg.get("content", []):
                if b.get("type") != "tool_use":
                    continue
                name, inp = b["name"], b.get("input", {})
                tools.append(name)
                if name == "Skill":
                    loads.append({"skill": str(inp.get("skill", "")).split(":")[-1], "ref": None, "step": step})
                    continue
                text = json.dumps(inp)
                for m in SKILL_PATH.finditer(text):
                    loads.append({"skill": m.group(1), "ref": m.group(3), "step": step})
                if name == "Read":
                    reads.append(str(inp.get("file_path", "")))
                elif name == "Bash":
                    reads.append("$ " + str(inp.get("command", ""))[:200])
        elif e.get("type") == "result":
            result = e
    return {"loads": loads, "reads": reads, "tools": tools, "steps": len(step_ids), "result": result}


CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def grade(case: dict, parsed: dict) -> dict:
    """`has` reads the whole reply; `lacks` reads only fenced code, so prose that warns
    against a pattern ("never `pkill -f`") does not count as using it."""
    loaded = {x["skill"] for x in parsed["loads"]}
    reply = parsed["result"].get("result", "") or ""
    code = "\n".join(CODE_BLOCK.findall(reply))
    fails = []
    for want in case.get("skills", []):
        if not loaded & set(want.split("|")):
            fails.append(f"skill not loaded: {want}")
    for bad in case.get("not_skills", []):
        if bad in loaded:
            fails.append(f"skill loaded: {bad}")
    for rx in case.get("has", []):
        if not re.search(rx, reply, re.MULTILINE):
            fails.append(f"missing: {rx}")
    for rx in case.get("lacks", []):
        if re.search(rx, code, re.MULTILINE):
            fails.append(f"present: {rx}")
    if parsed["result"].get("is_error") or not reply:
        fails.append("no reply: " + str(parsed["result"].get("subtype", "no result event")))
    return {"pass": not fails, "fails": fails, "loaded": sorted(loaded)}


def run_case(case: dict, i: int, args, base: Path, out: Path) -> dict:
    work_root = Path(tempfile.mkdtemp(prefix="probe-", dir=args.work))
    work = work_root / "app"
    shutil.copytree(base, work, symlinks=True)
    fixture = case.get("base", "new")
    if fixture != "new":
        shutil.copytree(HERE / "fixtures" / fixture, work, dirs_exist_ok=True)
    (work_root / "tmp").mkdir()
    mode = case.get("mode", "plan")
    suite = SUITE if mode == "plan" and case.get("suite", True) else ""
    prompt = case["prompt"] + suite + (PLAN if mode == "plan" else ANSWER)
    cmd = [
        "claude", "-p", prompt, "--model", args.model,
        "--output-format", "stream-json", "--verbose",
        "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence",
        "--max-turns", str(case.get("max_turns", args.max_turns)),
        "--allowedTools", *READ_ONLY, "--disallowedTools", *NO_WRITE,
    ]
    if args.effort:
        cmd += ["--effort", args.effort]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=work, env=clean_env(work_root / "tmp"), capture_output=True, text=True,
                          timeout=args.timeout)
    secs = round(time.time() - t0, 1)
    lines = proc.stdout.splitlines()
    parsed = parse_stream(lines)
    g = grade(case, parsed)
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True).stdout
    res = parsed["result"]
    rec = {
        "id": case["id"], "i": i, "model": args.model, "mode": mode, **g,
        "loads": parsed["loads"], "reads": parsed["reads"], "steps": parsed["steps"],
        "turns": res.get("num_turns"), "cost": res.get("total_cost_usd", 0.0), "secs": secs,
        "changed_files": changed.strip().splitlines(), "reply": res.get("result", ""),
        "stderr": proc.stderr[-2000:],
    }
    name = f"{case['id']}-{i}"
    (out / f"{name}.jsonl").write_text(proc.stdout)
    (out / f"{name}.json").write_text(json.dumps(rec, indent=1))
    shutil.rmtree(work_root, ignore_errors=True)
    mark = "ok  " if rec["pass"] else "FAIL"
    print(f"{mark} {name:28} ${rec['cost']:.3f} {rec['steps']:>2} steps  loaded={','.join(rec['loaded']) or '-'}"
          + ("" if rec["pass"] else "  " + "; ".join(rec["fails"])), flush=True)
    return rec


def report(out: Path) -> str:
    recs = [json.loads(p.read_text()) for p in sorted(out.glob("*.json")) if p.name != "meta.json"]
    meta = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
    cases = {c["id"]: c for c in meta.get("case_list", [])}
    current = HERE / "cases" / str(meta.get("cases", ""))
    if current.is_file():  # grade with today's patterns; a fixed regex applies to old runs
        for x in current.read_text().splitlines():
            if x.strip() and not x.startswith("//"):
                c = json.loads(x)
                cases[c["id"]] = c
        meta["case_list"] = list(cases.values())
    for r in recs:  # grade again, so a fixed pattern applies to old runs
        if r["id"] in cases:
            parsed = {"loads": r["loads"], "result": {"result": r["reply"], "is_error": False}}
            r.update(grade(cases[r["id"]], parsed))
    by: dict[str, list[dict]] = {}
    for r in recs:
        by.setdefault(r["id"], []).append(r)
    lines = [f"# Probe: {meta.get('cases', '?')} on {meta.get('model', '?')}", "",
             f"Kit {meta.get('kit', '?')} ({meta.get('kit_hash', '?')}), {len(recs)} runs, "
             f"pass {sum(r['pass'] for r in recs)}/{len(recs)}, cost ${sum(r['cost'] for r in recs):.2f}.", "",
             "| case | pass | median $ | steps | skills loaded (count over runs) | failures |",
             "|---|---|---:|---:|---|---|"]
    for cid, rs in by.items():
        rs.sort(key=lambda r: r["i"])
        costs = sorted(r["cost"] for r in rs)
        steps = sorted(r["steps"] for r in rs)
        loads: dict[str, int] = {}
        for r in rs:
            for s in r["loaded"]:
                loads[s] = loads.get(s, 0) + 1
        fails: dict[str, int] = {}
        for r in rs:
            for f in r["fails"]:
                fails[f] = fails.get(f, 0) + 1
        lines.append(
            f"| {cid} | {sum(r['pass'] for r in rs)}/{len(rs)} | {costs[len(costs) // 2]:.3f} | "
            f"{steps[len(steps) // 2]} | {', '.join(f'{k} {v}' for k, v in sorted(loads.items())) or '-'} | "
            f"{'; '.join(f'{k} ({v})' for k, v in fails.items()) or ''} |".replace("\n", " ")
        )
    # routing precision over every run: a load is expected when a case names it
    exp_total = hit = extra = 0
    for r in recs:
        case_skills = next((c for c in meta.get("case_list", []) if c["id"] == r["id"]), {})
        wanted = [set(w.split("|")) for w in case_skills.get("skills", [])]
        exp_total += len(wanted)
        hit += sum(1 for w in wanted if w & set(r["loaded"]))
        allowed = set().union(*wanted) if wanted else set()
        extra += len(set(r["loaded"]) - allowed - set(case_skills.get("ok_skills", [])))
    if exp_total:
        lines += ["", f"Routing: {hit}/{exp_total} expected loads happened; {extra} loads no case asked for."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="?")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--effort", default="high", help="'' for the model default")
    ap.add_argument("-n", type=int, default=1, help="runs per case")
    ap.add_argument("--kit", type=Path, default=KIT_DEFAULT, help="a stario-create checkout")
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", type=Path, default=HERE / "runs" / "probe")
    ap.add_argument("--work", default=None, help="parent dir for the throwaway apps")
    ap.add_argument("--report", type=Path, help="print the summary of an earlier run dir")
    args = ap.parse_args()
    if args.report:
        print(report(args.report))
        return
    if not args.cases:
        ap.error("cases is required")
    cases = [json.loads(x) for x in Path(args.cases).read_text().splitlines() if x.strip() and not x.startswith("//")]
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    kit = args.kit.resolve()
    args.work = args.work or tempfile.mkdtemp(prefix="stario-probe-")
    base = base_app(kit)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = args.out / f"{kit.name}-{Path(args.cases).stem}-{args.model.replace('claude-', '')}-{stamp}"
    out.mkdir(parents=True)
    (out / "meta.json").write_text(json.dumps({
        "kit": str(kit), "kit_hash": kit_hash(kit), "model": args.model, "effort": args.effort,
        "cases": Path(args.cases).name, "n": args.n, "case_list": cases,
        "claude": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
    }, indent=1))
    jobs = [(c, i) for i in range(1, args.n + 1) for c in cases]
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        futs = [ex.submit(run_case, c, i, args, base, out) for c, i in jobs]
        for f in cf.as_completed(futs):
            try:
                f.result()
            except Exception as err:  # one broken run must not stop the batch
                print(f"ERROR {err}", file=sys.stderr)
    summary = report(out)
    (out / "summary.md").write_text(summary)
    print("\n" + summary)
    print(out)


if __name__ == "__main__":
    main()
