#!/bin/sh
# run.sh VARIANT TASK N [MODEL]
# Copies the pristine scaffold, installs the variant guide and skills, runs one headless agent.
# VARIANT is `current` (this repo's AGENTS.md + skills/) or a dir containing AGENTS.md and skills/.
set -eu
variant=$1 task=$2 n=$3 model=${4:-swe-2-high}
here=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
root=${EVAL_DIR:-/tmp/stario-eval}
if [ "$variant" = "current" ]; then
    vsrc=$(CDPATH= cd -- "$here/.." && pwd)
    vid=current
else
    vsrc=$variant
    vid=$(basename "$variant")
fi
id="$vid-$task-$n-$model"
dir="$root/runs/$id"
mkdir -p "$root/runs"
rm -rf "$dir"
cp -R "$root/${BASE:-evalapp}" "$dir"
cd "$dir"
rm -f AGENTS.md
[ -f "$vsrc/AGENTS.md" ] && cp "$vsrc/AGENTS.md" AGENTS.md
rm -rf .agents/skills .claude/skills .cursor/skills && mkdir -p .agents/skills .claude/skills
[ -d "$vsrc/skills" ] && cp -R "$vsrc/skills/." .agents/skills/
for s in .agents/skills/*; do [ -e "$s" ] && ln -s "../../.agents/skills/$(basename "$s")" ".claude/skills/$(basename "$s")"; done
git add -A && git commit -qm "variant $variant" --allow-empty
uv sync -q >/dev/null 2>&1 || true
prompt="$(cat "$here/tasks/$task.md")"
start=$(date +%s)
"$here/dv" -p --respect-workspace-trust false --permission-mode dangerous --model "$model" \
  --export "$dir/.eval-transcript.md" -- "$prompt" >"$dir/.eval-out.txt" 2>&1 || echo "agent exit $?" >>"$dir/.eval-out.txt"
echo $(( $(date +%s) - start )) >"$dir/.eval-seconds"
uv run python "$here/check.py" "$dir" "$task" >"$dir/.eval-check.json" 2>&1 || true
echo "done $id"
